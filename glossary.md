# Global glossary

Terms that mean the same thing in every repository that runs doc-checks.
A repository's own glossary (`docs/glossary.md` or `glossary.md`) holds the
terms that belong to that project or client only, and never repeats a term
from here. To give a global term a different meaning in one repository, add a
row there that links to the global entry (see
[Global and local terms](README.md#global-and-local-terms)).

Each row is one term: an `<a id>` that links point to, the term (synonyms
separated by ` / `), and its meaning in plain words.

## AI tools <a id="ai-tools"></a>

| Term | Meaning |
| --- | --- |
| <a id="llm"></a>LLM | Large language model: the AI engine behind a chat assistant. |
| <a id="session"></a>Session / chat | One conversation with an AI assistant, which remembers only what was said in it. |
| <a id="context"></a>Context window / token / compaction | How much text the AI can keep in view at once. A token is the unit it counts in, about three quarters of a word. Compaction is summarizing earlier text to make room. |
| <a id="subagent"></a>Subagent | A helper AI started for one job, with its own separate conversation, that reports back when done. |
| <a id="mcp"></a>MCP / MCP server | Model Context Protocol: a standard way to give an AI app extra tools. An MCP server is a program that provides them. |
| <a id="skill"></a>Skill / slash command | A saved, step-by-step procedure an AI assistant can follow. A slash command, such as `/review`, starts one by name. |
| <a id="plugin"></a>Plugin / connector | A plugin is an add-on that extends an app. A connector is a signed-in link from an app to an outside service. |
| <a id="hook"></a>Hook | A command that runs automatically at a set moment, such as when a session starts or before a tool runs. |
| <a id="sandbox"></a>Sandbox | Limits on which files and network addresses a program may touch. |
| <a id="permissions"></a>Allow / ask / deny | The three answers a permission setting can give an action: run it, ask a person first, or block it. |
| <a id="transcript"></a>Transcript | The saved record of a conversation. |

## Engineering practice <a id="engineering-practice"></a>

| Term | Meaning |
| --- | --- |
| <a id="rollback"></a>Rollback | Steps that undo a change and return things to how they were. |
| <a id="runbook"></a>Runbook | Written step-by-step instructions for setting something up or recovering from a problem. |
| <a id="source-of-truth"></a>Source of truth / system of record | The one place whose version wins when copies disagree. |
| <a id="single-writer"></a>Single writer | Only one automatic process may change a given system, so changes never collide. |
| <a id="dry"></a>DRY | "Don't repeat yourself": each fact, rule or piece of logic has exactly one home, and everything else links to it. |
| <a id="yagni"></a>YAGNI | "You aren't gonna need it": build only what today's need requires. |
| <a id="monkey-patching"></a>Monkey patching | Changing how installed code behaves while it runs, or editing a dependency's files directly, instead of using a supported option. |
| <a id="idempotent"></a>Idempotent | Safe to run again: repeating it adds no extra effect. |
| <a id="preview"></a>Preview / dry-run | A run that shows what it would do and changes nothing. |
| <a id="credential"></a>Credential / API token | A secret, such as a password or key, that grants access to a system. |
| <a id="manifest"></a>Manifest | A file listing what a project needs, such as its dependencies. |
| <a id="cli"></a>CLI / PATH | A CLI is a program you run by typing a command. PATH is the list of folders where the computer looks for those programs. |
| <a id="formats"></a>JSON / TOML / YAML / frontmatter | Text formats for settings. Frontmatter is a settings block at the top of a Markdown file, between `---` lines. |
| <a id="symlink"></a>Symlink | A file-system shortcut that points to a real file or folder. |

## Git and GitHub <a id="git-and-github"></a>

| Term | Meaning |
| --- | --- |
| <a id="repository"></a>Repository / commit | A project folder whose history Git tracks. A commit is one saved snapshot of it. |
| <a id="branch"></a>Branch / main | A named line of changes. Main is the branch everything is combined into. |
| <a id="worktree"></a>Worktree | An extra working copy of the same repository, so two branches can be open at once. |
| <a id="push"></a>Push / remote / origin | Push uploads commits to another copy of the repository, called a remote. Origin is the usual name for the main remote. |
| <a id="force-push"></a>Force push | A push that overwrites history on the remote, which can erase other people's work. |
| <a id="pr"></a>PR / merge / auto-merge | A pull request proposes combining one branch into another. A merge combines them. Auto-merge does it once checks pass. |
| <a id="revert"></a>git revert | Undoes a commit by adding a new commit that reverses it, without rewriting history. |
| <a id="gh"></a>gh | GitHub's command-line program. |
| <a id="gitignore"></a>.gitignore | A file listing which files Git should not track. |
