#!/usr/bin/env python3
"""Check a repository's Markdown for broken interlinking and repeated text.

Run from anywhere: python3 -I check-links.py [--themes] [--skip NAME]... [repository root]
The root defaults to the current folder. Exit 1 with one line per finding, 0
when clean. Reads only.

--themes lists, instead of the checks below, the paragraph pairs in different
files that say the most similar things (shared vocabulary, weighted by how
rare each word is across the repository), best match first, with both
locations and the words they share. Run it before writing a new section: if
the idea already has a home, link there instead. It is a reading aid, not a
pass or fail, so it always exits 0.

Live documents are every .md file except hidden and node_modules folders,
symlinks (so a linked file is not read twice), files Git ignores when the root
is in a Git work tree, and everything a skip entry names. A skip entry is a
folder name, skipped at any depth, or a path from the root to one folder or
file (frozen history, another repository's raw material). Skipped files are
not checked, but links into them still are.

An optional .check-links.json at the root holds the repository's settings:

  {"skip": ["docs/archive", "HISTORY.md"],
   "aliases": ["~/Code/my-repo/"],
   "refs": {"Core": "rules.md"},
   "glossary": "docs/terms.md",
   "generated": ["CLAUDE.md", "AGENTS.md"],
   "similar_ok": [{"files": ["a.md", "b.md"], "reason": "each is read alone"}],
   "links": "lychee"}

skip adds to the --skip options. aliases are path prefixes that mean the root
in plain-text references. refs names documents that prose cites by a short
name, as in (Core, "Section"). glossary is the repository's own glossary,
found at docs/glossary.md or glossary.md when not set; a path outside the
repository, symlinks included, is refused. generated lists files written by a
tool from one source: their links are checked, but they never count as
duplicates of each other. similar_ok silences the NEAR warning for one pair of
files and needs a reason. links set to "lychee" leaves missing local files and
anchors to lychee; the checker still reports the rest.

--define TERM prints, instead of the checks, every row in the repository's
glossary and then the global glossary (glossary.md next to this script) whose
term starts with TERM. It exits 1 when none does. It reads only those two
glossaries, so one repository's terms never show up in another's lookup.

--vale DIR writes, instead of the checks, Vale's word lists under DIR: the
Global and Project vocabularies (every glossary term) and the Glossary
substitution rule (wording a row rejects with <!-- reject: a, b -->, replaced
by the row's first term). The rule sets vocab: false, so no vocabulary entry
can excuse rejected wording.

For each live document it reports:

- LINK: a relative link whose file is missing, or whose #fragment matches no
  heading and no <a id> in the target.
- UNSTABLE: a #fragment that resolves only through a heading's generated id.
  Give the heading an explicit id, `## Title <a id="title"></a>`, so the
  heading can be reworded without breaking links.
- REF: a plain-text section reference that names no heading or bold label
  in its target: `` `file.md`, "Section" ``, (Name, "Section") for a name in
  refs, or "Section" below/above in the same file. Paths outside the
  repository are skipped.
- DUP: a sentence of nine words or more that appears in two files. Give each
  rule one home and link to it from everywhere else.
- DEF: a glossary row (`| <a id="id"></a>Term / Synonym | Meaning |`) whose
  term another row of the same glossary already defines, or whose term the
  global glossary defines and whose meaning doesn't link the global entry.
  Links to the global glossary's URL are checked like relative links.

It also prints, without failing, NEAR warnings: paragraph pairs in different
files at least 0.6 similar by --themes' measure. Similarity is a reason to
read both places, not proof that they say the same thing.
"""
import argparse
import collections
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unicodedata

LINK = re.compile(r"\]\(([^)\s]+)\)")
HEADING = re.compile(r"(?m)^#{1,6}[ \t]+(.+?)[ \t]*$")
EXPLICIT_ID = re.compile(r'<a id="([^"]+)"')
FILE_REF = re.compile(r'`([\w./~-]+\.md)`(?: \([^)]*\))?,? "([^"]{2,60})"')
LOCAL_REF = re.compile(r'"([^"]{2,60})" (?:below|above)')
TERM_ROW = re.compile(r'(?m)^\|\s*<a id="([^"]+)"></a>([^|]+)\|([^\n]*)$')
REJECT = re.compile(r"<!--\s*reject:\s*(.*?)\s*-->")
CONFIG = ".check-links.json"
GLOBAL = str(Path(__file__).resolve().with_name("glossary.md"))
GLOBAL_URL = "https://github.com/Kerubi-5/doc-checks/blob/main/glossary.md"


def inside(root, path):
    """True when path, symlinks resolved, is root or below it."""
    real_root, real = os.path.realpath(root), os.path.realpath(path)
    return real == real_root or real.startswith(real_root + os.sep)


def settings(root, skip=()):
    """The root's .check-links.json, with --skip entries added to its skip list."""
    path = os.path.join(root, CONFIG)
    found = json.loads(Path(path).read_text(encoding="utf-8")) if os.path.exists(path) else {}
    glossary = found.get("glossary") or next(
        (g for g in ("docs/glossary.md", "glossary.md") if os.path.exists(os.path.join(root, g))), None)
    if glossary and not inside(root, os.path.join(root, glossary)):
        sys.exit(f"{CONFIG}: glossary {glossary} is outside the repository; only this repository's own "
                 "glossary and the global one may be read")
    for entry in found.get("similar_ok", []):
        if len(entry.get("files", [])) != 2 or not entry.get("reason", "").strip():
            sys.exit(f"{CONFIG}: each similar_ok entry needs two files and a reason: {entry}")
    return {"skip": [*found.get("skip", []), *skip], "aliases": found.get("aliases", []),
            "refs": found.get("refs", {}), "glossary": glossary and os.path.join(root, glossary),
            "generated": {os.path.normpath(g) for g in found.get("generated", [])},
            "lychee": found.get("links") == "lychee",
            "similar_ok": {frozenset(map(os.path.normpath, e["files"])) for e in found.get("similar_ok", [])}}


def terms(path):
    """(id, names, line, meaning, rejected) for each glossary row; synonyms in the term cell are split on ' / '.

    rejected lists the wording a <!-- reject: a, b --> comment in the row asks to replace with the term."""
    text = Path(path).read_text(encoding="utf-8")
    rows = []
    for m in TERM_ROW.finditer(visible(text)):
        rejected = [w.strip() for found in REJECT.findall(m[3]) for w in found.split(",") if w.strip()]
        rows.append((m[1], [n.strip() for n in m[2].split(" / ") if n.strip()],
                     text.count("\n", 0, m.start()) + 1, REJECT.sub("", m[3]).strip(" |"), rejected))
    return rows


def glossaries(config, shared=GLOBAL):
    """(path, terms) for the repository's glossary, then the global one; the same file only once."""
    paths = [p for p in (config["glossary"], shared) if p and os.path.exists(p)]
    if len(paths) == 2 and os.path.samefile(*paths):
        paths = paths[1:]
    return [(p, terms(p)) for p in paths]


def definitions(root, config, shared=GLOBAL):
    """DEF findings: a term defined twice in one glossary, or a global term redefined without saying so."""
    found = []
    tables = glossaries(config, shared)
    for path, rows in tables:
        first = {}
        for _, names, line, _, _ in rows:
            for name in map(str.lower, names):
                if name in first:
                    found.append(f'DEF {os.path.relpath(path, root)}:{line}: "{name}" is already defined on line {first[name]}')
                first.setdefault(name, line)
    if len(tables) == 2:
        (local, rows), (_, shared) = tables
        shared_ids = {name.lower(): term_id for term_id, names, _, _, _ in shared for name in names}
        for _, names, line, meaning, _ in rows:
            for name in map(str.lower, names):
                if name in shared_ids and GLOBAL_URL not in meaning:
                    found.append(f'DEF {os.path.relpath(local, root)}:{line}: "{name}" is a global term; '
                                 f"remove the row, or link {GLOBAL_URL}#{shared_ids[name]} to mark a local meaning")
    return found


def define(root, word, skip=(), shared=GLOBAL):
    """Print every glossary row, the repository's first, whose term starts with word."""
    root = os.path.abspath(root)
    word = word.strip().lower()
    hits = 0
    for path, rows in glossaries(settings(root, skip), shared):
        where = "global" if path == shared else os.path.relpath(path, root)
        for _, names, line, meaning, _ in rows:
            if any(n.lower().startswith(word) for n in names):
                print(f"{' / '.join(names)} ({where}:{line}): {meaning}")
                hits += 1
    if not hits:
        print(f'No glossary defines "{word}".')
    return 0 if hits else 1


def git_files(root):
    """Paths under root, relative to it, that Git tracks or doesn't ignore; None without Git or a work tree."""
    try:
        listed = subprocess.run(["git", "-C", root, "ls-files", "-co", "--exclude-standard", "-z"],
                                capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    # Git prints composed Unicode on macOS; the file system may hand back decomposed names.
    return {unicodedata.normalize("NFC", os.fsdecode(p)) for p in listed.split(b"\0") if p}


def live_files(root, skip=()):
    root = os.path.abspath(root)
    allowed = git_files(root)
    paths = {os.path.normpath(s) for s in skip}
    for folder, directories, names in os.walk(root):
        rel = os.path.relpath(folder, root)
        directories[:] = [name for name in directories
                          if not name.startswith(".") and name != "node_modules" and name not in skip
                          and os.path.normpath(os.path.join(rel, name)) not in paths]
        for name in names:
            path = os.path.join(folder, name)
            if (name.endswith(".md") and os.path.normpath(os.path.join(rel, name)) not in paths
                    and not os.path.islink(path)
                    and (allowed is None
                         or unicodedata.normalize("NFC", os.path.relpath(path, root)) in allowed)):
                yield path


def markdown_lines(text, omit_inline=False):
    """Keep line numbers while blanking frontmatter and fenced code."""
    frontmatter, fence = text.startswith("---\n") or text.startswith("---\r\n"), None
    for number, line in enumerate(text.splitlines(), 1):
        if frontmatter:
            if number > 1 and line.strip() in ("---", "..."):
                frontmatter = False
            yield number, ""
            continue
        marker = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            yield number, ""
            continue
        if marker:
            fence = marker[1]
            yield number, ""
            continue
        yield number, re.sub(r"(`+).*?\1", "", line) if omit_inline else line


def visible(text, omit_inline=False):
    """markdown_lines joined back into one string."""
    return "\n".join(line for _, line in markdown_lines(text, omit_inline))


def prose(text):
    """Yield normalized paragraphs, keeping separate list items separate."""
    buffer, start = [], 0
    for number, line in markdown_lines(text):
        item = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", line)
        excluded = re.match(r"^\s*(?:#{1,6}\s|\||(?:[-*_]\s*){3,}$)", line)
        if buffer and (not line.strip() or excluded or item):
            yield start, " ".join(buffer)
            buffer = []
        if line.strip() and not excluded:
            if not buffer:
                start = number
            line = line[item.end():] if item else line
            buffer.append(re.sub(r"\]\([^)]*\)", "]", line.strip()))
    if buffer:
        yield start, " ".join(buffer)


def heading_id(text):
    """GitHub's generated anchor for a heading."""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[`*_\[\]()]", "", text).strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def anchors(text):
    explicit = set(EXPLICIT_ID.findall(visible(text, omit_inline=True)))
    generated = {heading_id(h) for h in HEADING.findall(visible(text))}
    return explicit, generated


def labels(text):
    """Lowercased headings (tags and numbering removed) and bold labels a reference may name."""
    body = visible(text)
    found = [re.sub(r"<[^>]+>|[`*]", "", h) for h in HEADING.findall(body)]
    found += re.findall(r"\*\*([^*]+?)\*\*", body)
    return {re.sub(r"^[\d.]+\s+", "", x).strip(" :.").lower() for x in found}


def references(path, text, root, config):
    """(target file, section) for each plain-text section reference; wrapped lines joined."""
    body = re.sub(r"\s+", " ", visible(text))
    for ref, section in FILE_REF.findall(body):
        alias = next((a for a in config["aliases"] if ref.startswith(a)), None)
        if ref.startswith("~") and alias is None:
            continue
        for base in (os.path.dirname(path), root):
            target = os.path.normpath(os.path.join(base, ref[len(alias):] if alias else ref))
            if os.path.exists(target):
                yield target, section
                break
    for name, document in config["refs"].items():
        for section in re.findall(re.escape(name) + r'(?:,|\'s) \(?"([^"]{2,60})"', body):
            yield os.path.join(root, document), section
    for section in LOCAL_REF.findall(body):
        yield path, section


URL = re.compile(r"https?://\S+")


def sentences(text):
    for _, body in prose(text):
        for raw in re.split(r"(?<=[.;:])\s+", URL.sub("", body)):
            words = re.sub(r"\s+", " ", re.sub(r"[`*_\[\]()>|#-]", "", raw)).strip().lower()
            if len(words.split()) >= 9:
                yield words


# Negations (no, not, never) stay in: "do X" and "never do X" must not look alike.
STOPWORDS = set("""a an and are as at be but by for from has have if in into is it its of
on or so that the their then there these this to was when which with your you
one two any each every only also than after before over under out up down all what who how why
where does did do done can may must ever same other such more most into onto via per""".split())
MIN_WORDS = 20      # shorter paragraphs are pointers or headings, not restatements
MIN_SCORE = 0.3     # cosine similarity; pairs below this are usually just shared vocabulary
NEAR_SCORE = 0.6    # a NEAR warning; calibrated so that only near-copies, not shared topics, reach it
MAX_PAIRS = 25


def paragraphs(path, text):
    """(file, first line, words) for each prose paragraph; code, tables and URLs skipped."""
    result = []
    for line, body in prose(text):
        words = [w for w in re.findall(r"[a-z][a-z'-]{2,}", URL.sub("", body).lower()) if w not in STOPWORDS]
        if len(words) >= MIN_WORDS:
            result.append((path, line, words))
    return result


def similar(files, minimum):
    """(score, unit, unit, shared words) for paragraph pairs in different files, most similar first."""
    import math
    units = []
    for f in files:
        if f.endswith("glossary.md"):
            continue  # its rows summarize every owner on purpose
        units += paragraphs(f, Path(f).read_text(encoding="utf-8"))
    frequency = collections.Counter()
    for _, _, words in units:
        frequency.update(set(words))
    total = len(units)
    vectors = []
    for _, _, words in units:
        counts = collections.Counter(words)
        vector = {w: (1 + math.log(c)) * math.log(total / frequency[w]) for w, c in counts.items()
                  if frequency[w] > 1}
        norm = math.sqrt(sum(v * v for v in vector.values())) or 1.0
        vectors.append({w: v / norm for w, v in vector.items()})
    pairs = []
    for i in range(len(units)):
        for j in range(i + 1, len(units)):
            if units[i][0] == units[j][0]:
                continue
            a, b = vectors[i], vectors[j]
            if len(a) > len(b):
                a, b = b, a
            score = sum(v * b[w] for w, v in a.items() if w in b)
            if score >= minimum:
                shared = sorted((w for w in a if w in b), key=lambda w: -(a[w] * b[w]))[:6]
                pairs.append((score, units[i], units[j], shared))
    pairs.sort(key=lambda p: -p[0])
    return units, pairs


def themes(root, skip=()):
    root = os.path.abspath(root)
    files = sorted(live_files(root, settings(root, skip)["skip"]))
    units, pairs = similar(files, MIN_SCORE)
    for score, (fa, la, _), (fb, lb, _), shared in pairs[:MAX_PAIRS]:
        print(f"{score:.2f} {os.path.relpath(fa, root)}:{la} ~ {os.path.relpath(fb, root)}:{lb}"
              f"  [{', '.join(shared)}]")
    print(f"{len(units)} paragraphs in {len(files)} files, {len(pairs)} pairs at or above {MIN_SCORE}")
    return 0


def vocabulary_entry(name):
    """A Vale vocabulary pattern: ordinary words match in any case, names like KairOS or LLM only as written."""
    pattern = re.escape(name).replace("\\ ", " ")
    plain = name == name.lower() or name == name[0].upper() + name[1:].lower()
    return f"(?i){pattern}" if plain else pattern


def vale(root, out, skip=(), shared=GLOBAL):
    """Write Vale's Global and Project vocabularies and the Glossary substitution rule under out."""
    root = os.path.abspath(root)
    out = os.path.join(root, out)
    if not inside(root, out):
        sys.exit(f"--vale {out} is outside the repository")
    config = settings(root, skip)
    swap = {}
    lists = {"Global": [], "Project": []}
    for path, rows in glossaries(config, shared):
        layer = "Global" if path == shared else "Project"
        for _, names, _, _, rejected in rows:
            lists[layer] += [vocabulary_entry(n) for n in names]
            for wording in rejected:
                swap[wording.lower()] = names[0]
    for layer, entries in lists.items():
        folder = os.path.join(out, "config", "vocabularies", layer)
        os.makedirs(folder, exist_ok=True)
        Path(folder, "accept.txt").write_text("".join(f"{e}\n" for e in sorted(set(entries))), encoding="utf-8")
    os.makedirs(os.path.join(out, "Glossary"), exist_ok=True)
    rule = ["# Generated by doc-checks from the glossaries' <!-- reject: ... --> comments; do not edit.",
            "extends: substitution", "message: \"Use '%s' instead of '%s' (glossary).\"",
            "level: error", "ignorecase: true",
            "# An accepted vocabulary word must never excuse rejected wording.", "vocab: false"]
    rule += ["swap:"] + [f"  {json.dumps(k)}: {json.dumps(v)}" for k, v in sorted(swap.items())] if swap else ["swap: {}"]
    Path(out, "Glossary", "Substitutions.yml").write_text("\n".join(rule) + "\n", encoding="utf-8")
    print(f"{sum(map(len, lists.values()))} vocabulary entries, {len(swap)} substitutions written to "
          f"{os.path.relpath(out, root)}")
    return 0


def main(root, skip=(), shared=GLOBAL):
    root = os.path.abspath(root)
    config = settings(root, skip)
    files = sorted(live_files(root, config["skip"]))
    texts = {f: Path(f).read_text(encoding="utf-8") for f in files}
    generated = {os.path.join(root, g) for g in config["generated"]}
    ids = {}
    names = {}
    findings = []
    seen = collections.defaultdict(set)
    for f, text in texts.items():
        rel = os.path.relpath(f, root)
        for link in LINK.findall(visible(text, omit_inline=True)):
            path, _, fragment = link.partition("#")
            if path == GLOBAL_URL:
                target = shared
            elif link.startswith(("http://", "https://", "mailto:")):
                continue
            else:
                target = f if not path else os.path.normpath(os.path.join(os.path.dirname(f), path))
            local = path != GLOBAL_URL
            if path and not os.path.exists(target):
                if not (local and config["lychee"]):
                    findings.append(f"LINK {rel}: {link} (missing file)")
                continue
            if not fragment or not target.endswith(".md") or not os.path.isfile(target):
                continue
            if target not in ids:  # skipped files are link targets too
                ids[target] = anchors(texts.get(target) or Path(target).read_text(encoding="utf-8"))
            explicit, generated_ids = ids[target]
            if fragment in explicit:
                continue
            if fragment in generated_ids:
                findings.append(f"UNSTABLE {rel}: {link} (heading has no <a id>)")
            elif not (local and config["lychee"]):
                findings.append(f"LINK {rel}: {link} (missing anchor)")
        for target, section in references(f, text, root, config):
            if target not in names:
                names[target] = labels(Path(target).read_text(encoding="utf-8"))
            if not any(n.startswith(section.lower()) for n in names[target]):
                findings.append(f'REF {rel}: "{section}" ({os.path.relpath(target, root)} has no such section)')
        for sentence in sentences(text):
            seen[sentence].add(f)
    for sentence, where in seen.items():
        # Generated copies of one source count as one place, so they never duplicate each other.
        if len({p if p not in generated else "generated" for p in where}) > 1:
            findings.append(f"DUP {', '.join(sorted(os.path.relpath(p, root) for p in where))}: {sentence[:100]}")
    findings += definitions(root, config, shared)
    findings = list(dict.fromkeys(findings))  # the same link twice in a file: one line
    warnings = []
    for score, (fa, la, _), (fb, lb, _), shared_words in similar(files, NEAR_SCORE)[1]:
        pair = frozenset((os.path.relpath(fa, root), os.path.relpath(fb, root)))
        if (fa in generated and fb in generated) or pair in config["similar_ok"]:
            continue
        warnings.append(f"NEAR (warning) {os.path.relpath(fa, root)}:{la} ~ {os.path.relpath(fb, root)}:{lb}"
                        f" {score:.2f} [{', '.join(shared_words)}]")
    for line in findings + warnings:
        print(line)
    print(f"{len(files)} files checked, {len(findings)} findings, {len(warnings)} warnings")
    return 1 if findings else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--themes", action="store_true")
    parser.add_argument("--define", metavar="TERM")
    parser.add_argument("--vale", metavar="DIR")
    parser.add_argument("--skip", action="append", default=[], metavar="NAME")
    parser.add_argument("root", nargs="?", default=".")
    options = parser.parse_args()
    if options.define:
        sys.exit(define(options.root, options.define, options.skip))
    if options.vale:
        sys.exit(vale(options.root, options.vale, options.skip))
    sys.exit((themes if options.themes else main)(options.root, options.skip))
