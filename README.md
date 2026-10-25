# doc-checks

One Markdown checker shared by many repositories, so each one checks its docs
the same way instead of keeping its own copy. It finds broken links and
anchors, links that break when a heading is reworded, plain-text section
references that point nowhere, and sentences repeated across files. With
`--themes` it lists paragraphs in different files that say similar things.
`python3 check-links.py --help` explains each finding and how to fix it.

## Add it to a repository <a id="adopt"></a>

1. Add one step to a GitHub Actions job, after the checkout:

   ```yaml
   - uses: actions/checkout@v7
     with:
       persist-credentials: false
   - uses: Kerubi-5/doc-checks@main
   ```

2. If some folders or files shouldn't be checked (build output, frozen
   history), list them in `.check-links.json` at the repository root. The
   settings are described in `python3 check-links.py --help`:

   ```json
   {"skip": ["dist", "docs/archive"]}
   ```

3. Run it locally from the repository root with a clone of this repository:

   ```bash
   python3 -I ~/Code/doc-checks/check-links.py
   ```

Fix what it finds, then remove any older link or repeated-text checks the
repository had, so only one checker remains.

## Global and local terms <a id="global-and-local-terms"></a>

Definitions live in two layers, and meaning only flows one way:

- **Global:** [glossary.md](glossary.md) in this repository. It holds terms
  that mean the same everywhere, written so anyone can read them. It never
  links to or names a project or client.
- **Local:** each repository's own glossary (`docs/glossary.md` or
  `glossary.md`). It holds terms that belong to that project or client, and
  links to global terms instead of repeating them:
  `[rollback](https://github.com/Kerubi-5/doc-checks/blob/main/glossary.md#rollback)`.

A repository with its own meaning for a global term adds a row whose meaning
links to the global entry, which marks the difference as deliberate. A row
that repeats a global term without that link is a DEF finding.

To look up a term from a repository, run the following from its root. It
prints the repository's own meaning first, then the global one, and never
reads another repository:

```bash
python3 -I ~/Code/doc-checks/check-links.py --define rollback
```

## Develop <a id="develop"></a>

```bash
python3 -I test_check_links.py
```

Every repository using `@main` runs the latest version, so a change here
reaches all of them at once. Run the tests before pushing.
