"""Offline regressions for Markdown coverage and prose extraction."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("check-links.py")
spec = importlib.util.spec_from_file_location("check_links", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def write(root, *names, text="text\n"):
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


class CheckLinksTests(unittest.TestCase):
    def check(self, root):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = checker.main(str(root))
        return status, output.getvalue()

    def found(self, root, skip=()):
        return {str(Path(p).relative_to(root)) for p in checker.live_files(root, skip)}

    def run_cli(self, *args, path=None):
        env = dict(os.environ, PATH=path) if path is not None else None
        return subprocess.run([sys.executable, "-I", str(SCRIPT), *args],
                              capture_output=True, text=True, env=env)

    def test_symlinked_files_are_read_once(self):
        sentence = "This sentence contains enough distinct words to exercise duplicate detection correctly.\n"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root, "AGENTS.md", text=sentence)
            (root / "CLAUDE.md").symlink_to("AGENTS.md")
            self.assertEqual(self.found(root), {"AGENTS.md"})
            self.assertEqual(self.check(root), (0, "1 files checked, 0 findings, 0 warnings\n"))

    @unittest.skipUnless(shutil.which("git"), "needs git")
    def test_git_ignored_files_are_skipped_inside_a_work_tree(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root, "README.md", "kept/b.md", "ignored/a.md", "secret.md", "forced.md")
            (root / ".gitignore").write_text("ignored/\nsecret.md\nforced.md\n")
            git = ["git", "-C", folder]
            subprocess.run(git + ["init", "-q"], check=True)
            subprocess.run(git + ["add", "-f", "forced.md"], check=True)  # tracked despite the ignore rule
            self.assertEqual(self.found(root), {"README.md", "kept/b.md", "forced.md"})
            self.assertEqual(self.found(root / "kept"), {"b.md"})  # a root below the work tree's top
            with tempfile.TemporaryDirectory() as empty:  # no git on PATH: today's plain walk
                result = self.run_cli(folder, path=empty)
            self.assertEqual((result.returncode, result.stdout), (0, "5 files checked, 0 findings, 0 warnings\n"))

    def test_skip_option_prunes_named_folders_at_any_depth(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root, "keep.md", "Sources/a.md", "nested/Sources/b.md", "Sourcesish/c.md",
                  "nested/_evidence/d.md", "notes/Sources.md")
            self.assertEqual(self.found(root, ("Sources", "_evidence")),
                             {"keep.md", "Sourcesish/c.md", "notes/Sources.md"})
            result = self.run_cli("--skip", "Sources", "--skip", "_evidence", folder)
            self.assertEqual((result.returncode, result.stdout), (0, "3 files checked, 0 findings, 0 warnings\n"))
            result = self.run_cli("--themes", "--skip", "Sources", folder)
            self.assertEqual((result.returncode, result.stdout.splitlines()[-1]),
                             (0, "0 paragraphs in 4 files, 0 pairs at or above 0.3"))

    def test_root_files_and_core_anchors_are_checked_from_relative_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(os.path.relpath(folder))
            (root / "operating-contract.md").write_text("## Safety boundaries\n")
            (root / "README.md").write_text("[Core](operating-contract.md#safety-boundaries)\n[bad](missing.md)\n")
            status, output = self.check(root)
            self.assertEqual(status, 1)
            self.assertIn("UNSTABLE README.md:", output)
            self.assertIn("LINK README.md: missing.md", output)
            (root / "operating-contract.md").write_text('## Safety <a id="safety-boundaries"></a>\n')
            (root / "README.md").write_text("[Core](operating-contract.md#safety-boundaries)\n")
            self.assertEqual(self.check(root)[0], 0)

    def test_prunes_exact_directory_components_without_skipping_similar_names(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            names = ("README.md", "SAFETY.md", "docs/archive/old.md", "docs/archived/live.md",
                     "node_modules/pkg/a.md", "node_modules-notes/a.md", ".hidden/a.md",
                     "nested/.hidden/a.md", "nested/SAFETY.md")
            write(root, *names)
            self.assertEqual(self.found(root, ("docs/archive", "SAFETY.md")),
                             {"README.md", "docs/archived/live.md", "node_modules-notes/a.md", "nested/SAFETY.md"})

    def test_wrapped_duplicate_matches_and_list_items_remain_separate(self):
        sentence = "This sentence contains enough distinct words to exercise duplicate detection correctly."
        wrapped = sentence.replace("distinct words", "distinct\nwords")
        self.assertEqual(list(checker.sentences(sentence)), list(checker.sentences(wrapped)))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "a.md").write_text(sentence)
            (root / "b.md").write_text(wrapped)
            status, output = self.check(root)
            self.assertEqual(status, 1)
            self.assertIn("DUP a.md, b.md:", output)
        self.assertEqual(list(checker.prose("- first short item\n  continued\n- second short item")),
                         [(1, "first short item continued"), (3, "second short item")])

    def test_shared_extractor_omits_metadata_code_headings_and_tables(self):
        noise = " ".join("metadataword" + str(i) for i in range(30))
        text = (f"---\ndescription: {noise}\n---\n# {noise}\n| {noise} |\n"
                f"   ```text\n{noise}\n   ```\n  ~~~~\n{noise}\n  ~~~~\n")
        self.assertEqual(list(checker.sentences(text)), [])
        self.assertEqual(checker.paragraphs("test.md", text), [])
        body = "Fresh prose carries enough distinct words to compare semantic content across several different documents without metadata polluting these paragraph vectors and making misleading matches appear."
        self.assertEqual(checker.paragraphs("test.md", text + body)[0][1], 12)

    def test_code_link_examples_and_fake_anchors_are_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "README.md").write_text(
                '`[example](missing.md)` and `<a id="inline-example"></a>`\n  ```md\n[example](missing.md)\n'
                '## Fake <a id="fake"></a>\n  ```\n[bad](#fake)\n')
            status, output = self.check(root)
            self.assertEqual(status, 1)
            self.assertNotIn("missing.md", output)
            self.assertIn("#fake (missing anchor)", output)
        self.assertEqual(checker.anchors("## The `kairos` command\n")[1], {"the-kairos-command"})
        self.assertEqual(checker.anchors('`<a id="inline-example"></a>`')[0], set())


    def test_plain_text_section_references_are_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "docs").mkdir()
            (root / ".check-links.json").write_text('{"skip": ["SAFETY.md"], "refs": {"Core": "operating-contract.md"}}')
            (root / "operating-contract.md").write_text("## Safety boundaries <a id=\"s\"></a>\n")
            (root / "SAFETY.md").write_text('> <a id="standard-rollback"></a>Rollback.\n')
            (root / "docs" / "guide.md").write_text(
                "## 2. Tools\n- **Cleanup:** text\n")
            (root / "README.md").write_text(
                '(`docs/guide.md`, "Tools") and\n(Core, "Safety\nboundaries"), "Cleanup" below,\n'
                '[rollback](SAFETY.md#standard-rollback), (`~/Code/kairos/CLAUDE.md`, "Elsewhere").\n'
                '## Cleanup <a id="cleanup"></a>\n')
            self.assertEqual(self.check(root), (0, "3 files checked, 0 findings, 0 warnings\n"))
            (root / "README.md").write_text(
                '(`docs/guide.md`, "Setup"), Core\'s "Change safety", "Profile" above.\n')
            status, output = self.check(root)
            self.assertEqual(status, 1)
            for name in ("Setup", "Change safety", "Profile"):
                self.assertIn(f'REF README.md: "{name}"', output)

    def test_settings_file_aliases_and_skipped_link_targets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".check-links.json").write_text('{"skip": ["docs/archive"], "aliases": ["~/Code/repo/"]}')
            write(root, "docs/archive/old.md", text="## Old title\n")
            write(root, "guide.md", text="## Setup <a id=\"setup\"></a>\n")
            write(root, "README.md", text='(`~/Code/repo/guide.md`, "Setup"), (`~/Code/other/x.md`, "Gone").\n')
            self.assertEqual(self.check(root), (0, "2 files checked, 0 findings, 0 warnings\n"))
            write(root, "README.md", text='(`~/Code/repo/guide.md`, "Teardown") [old](docs/archive/old.md#old-title)\n')
            status, output = self.check(root)
            self.assertEqual(status, 1)
            self.assertIn('REF README.md: "Teardown"', output)
            self.assertIn("UNSTABLE README.md: docs/archive/old.md#old-title", output)

    def test_root_defaults_to_the_current_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            write(Path(folder), "README.md", text="[bad](missing.md)\n")
            result = subprocess.run([sys.executable, "-I", str(SCRIPT)], cwd=folder, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("LINK README.md: missing.md", result.stdout)

    def test_glossary_terms_are_defined_once_and_global_terms_not_repeated(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shared = root / "global.md"
            shared.write_text('| <a id="rollback"></a>Rollback / Undo | Steps that undo a change. |\n')
            write(root, "repo/docs/glossary.md", text=(
                '| Term | Meaning |\n| --- | --- |\n'
                '| <a id="widget"></a>Widget | A part. |\n'
                '| <a id="gadget"></a>Gadget / widget | Another part. |\n'
                f'| <a id="undo"></a>Undo | Here it means revert. [Global]({checker.GLOBAL_URL}#rollback) |\n'
                '| <a id="rollback"></a>Rollback | Our own copy. |\n'))
            write(root, "repo/README.md", text=f"[ok]({checker.GLOBAL_URL}#rollback) [bad]({checker.GLOBAL_URL}#nope)\n")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = checker.main(str(root / "repo"), shared=str(shared))
            lines = output.getvalue().splitlines()
            self.assertEqual(status, 1)
            self.assertEqual(lines[:-1], [
                f"LINK README.md: {checker.GLOBAL_URL}#nope (missing anchor)",
                'DEF docs/glossary.md:4: "widget" is already defined on line 3',
                'DEF docs/glossary.md:6: "rollback" is a global term; remove the row, '
                f"or link {checker.GLOBAL_URL}#rollback to mark a local meaning"])

    def test_define_prints_the_repository_meaning_then_the_global_one(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shared = root / "global.md"
            shared.write_text('| <a id="rollback"></a>Rollback | Steps that undo a change. |\n')
            write(root, "repo/glossary.md", text='| <a id="r"></a>Rollback window | One hour. |\n')
            write(root, "other/glossary.md", text='| <a id="r"></a>Rollback plan | Client secret. |\n')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = checker.define(str(root / "repo"), "ROLL", shared=str(shared))
            self.assertEqual((status, output.getvalue()), (0,
                "Rollback window (glossary.md:1): One hour.\nRollback (global:1): Steps that undo a change.\n"))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(checker.define(str(root / "repo"), "deploy", shared=str(shared)), 1)
        result = self.run_cli("--define", "zzz-no-such-term", str(SCRIPT.parent))
        self.assertEqual((result.returncode, result.stdout), (1, 'No glossary defines "zzz-no-such-term".\n'))

    PARAGRAPH = ("Every scheduled report gathers invoices from accounting, reconciles payments against bank "
                 "statements, flags mismatched totals, emails finance reviewers, archives approved batches, "
                 "and records audit notes before closing the monthly ledger period.")

    def test_near_duplicates_warn_with_both_locations_without_failing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root, "a.md", text="# A\n\n" + self.PARAGRAPH + "\n")
            write(root, "b.md", text=self.PARAGRAPH.replace("emails finance", "notifies finance") + "\n")
            write(root, "c.md", text="Unrelated words about gardening, tomatoes, compost, watering, sunlight, "
                                     "pruning, mulch, seedlings, harvest, trellis, aphids, ladybugs, soil, "
                                     "worms, rain, shade, frost, seeds, greenhouse.\n")
            status, output = self.check(root)
            self.assertEqual(status, 0)
            self.assertIn("NEAR (warning) a.md:3 ~ b.md:1", output)
            self.assertTrue(output.endswith("3 files checked, 0 findings, 1 warnings\n"))
            (root / ".check-links.json").write_text('{"similar_ok": [{"files": ["b.md", "a.md"], "reason": "test"}]}')
            self.assertNotIn("NEAR", self.check(root)[1])
            (root / ".check-links.json").write_text('{"similar_ok": [{"files": ["b.md", "a.md"]}]}')
            with self.assertRaises(SystemExit):
                self.check(root)
        self.assertNotEqual(checker.paragraphs("x", "never " + self.PARAGRAPH)[0][2],
                            checker.paragraphs("x", self.PARAGRAPH)[0][2])  # negation is kept

    def test_generated_copies_only_duplicate_authored_text(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".check-links.json").write_text('{"generated": ["CLAUDE.md", "AGENTS.md"]}')
            write(root, "CLAUDE.md", "AGENTS.md", text=self.PARAGRAPH + "\n")
            self.assertEqual(self.check(root), (0, "2 files checked, 0 findings, 0 warnings\n"))
            write(root, "docs/guide.md", text=self.PARAGRAPH + "\n")
            status, output = self.check(root)
            self.assertEqual(status, 1)
            self.assertIn("DUP AGENTS.md, CLAUDE.md, docs/guide.md:", output)

    def test_glossary_paths_outside_the_repository_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root, "client/glossary.md", text='| <a id="x"></a>Secret | Client only. |\n')
            write(root, "repo/README.md")
            (root / "repo" / ".check-links.json").write_text('{"glossary": "../client/glossary.md"}')
            with self.assertRaises(SystemExit):
                self.check(root / "repo")
            (root / "repo" / "terms.md").symlink_to(root / "client" / "glossary.md")
            (root / "repo" / ".check-links.json").write_text('{"glossary": "terms.md"}')
            with self.assertRaises(SystemExit):
                self.check(root / "repo")

    def test_links_handed_to_lychee_skip_only_local_link_findings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shared = root / "global.md"
            shared.write_text('| <a id="r"></a>Rollback | Undo. |\n')
            write(root, "repo/a.md", text="## Old title\n")
            write(root, "repo/README.md", text=(
                f"[m](missing.md) [x](a.md#nope) [u](a.md#old-title) [g]({checker.GLOBAL_URL}#gone)\n"))
            (root / "repo" / ".check-links.json").write_text('{"links": "lychee"}')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                checker.main(str(root / "repo"), shared=str(shared))
            self.assertEqual(output.getvalue().splitlines()[:-1], [
                "UNSTABLE README.md: a.md#old-title (heading has no <a id>)",
                f"LINK README.md: {checker.GLOBAL_URL}#gone (missing anchor)"])

    def test_vale_files_come_from_glossary_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shared = root / "global.md"
            shared.write_text('| <a id="llm"></a>LLM | A model. |\n| <a id="r"></a>Rollback | Undo. |\n')
            write(root, "repo/glossary.md", text=(
                '| <a id="k"></a>KairOS / .gitignore | An app. <!-- reject: Kairos app, kairos-app --> |\n'))
            with contextlib.redirect_stdout(io.StringIO()):
                checker.vale(str(root / "repo"), ".vale/styles", shared=str(shared))
            styles = root / "repo" / ".vale" / "styles"
            self.assertEqual((styles / "config/vocabularies/Global/accept.txt").read_text(), "(?i)LLM\n(?i)Rollback\n")
            self.assertEqual((styles / "config/vocabularies/Project/accept.txt").read_text(), "(?i)KairOS\n(?i)\\.gitignore\n")
            rule = (styles / "Glossary/Substitutions.yml").read_text()
            self.assertIn("vocab: false\n", rule)
            self.assertIn('  "kairos app": "KairOS"\n  "kairos-app": "KairOS"\n', rule)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                checker.define(str(root / "repo"), "kairos", shared=str(shared))
            self.assertEqual(output.getvalue(), "KairOS / .gitignore (glossary.md:1): An app.\n")
            shared.write_text("")
            write(root, "repo/glossary.md", text='| <a id="k"></a>KairOS | An app. |\n')
            with contextlib.redirect_stdout(io.StringIO()):
                checker.vale(str(root / "repo"), ".vale/styles", shared=str(shared))
            self.assertIn("swap: {}\n", (styles / "Glossary/Substitutions.yml").read_text())


if __name__ == "__main__":
    unittest.main()
