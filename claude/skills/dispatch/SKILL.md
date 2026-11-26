---
name: dispatch
description: Run only when the user types /dispatch (Codex: $dispatch) or explicitly asks to turn dispatcher mode on or off. While it is on, every task the user gives runs in a background worker and the main chat stays free for questions, updates and new tasks. `/dispatch off` ends it.
disable-model-invocation: true
---

# Dispatch: tasks go to background workers, the chat stays free

The user wants to keep handing you tasks without waiting for the last one. You brief a worker for each,
answer the user's questions yourself, and check every result before you call it done.

| Typed | What you do |
|---|---|
| `/dispatch` or `/dispatch on` | Turn the mode on. Confirm in one line, and say once that each worker starts cold on your model, so several at once use the usage limit several times as fast. |
| `/dispatch off` | Take no new tasks into workers. Workers already running finish and are reported as below. Say what is still running. |
| `/dispatch status` | List every task as running, queued or done, one line each. |

The mode lasts until `/dispatch off` or the end of the session. Everything below applies while it is on.

## 1. When the user gives a task

- **Answer it yourself** when it is a question, or a change you can finish in a few tool calls. A worker
  for that costs more than the work.
- **Otherwise dispatch it.** Brief the worker with the outcome contract in `orchestrating-work`
  section 2: the objective, the files it owns, the user's standing rules, the acceptance criteria, how
  to verify them, when to stop and report, and what to return. The worker knows nothing you do not
  write down.
- **Same model and effort as you**, unless the user names another. On Claude Code leave `model` unset
  so the worker inherits yours, and set `run_in_background: true`.
- **Then confirm in one line and end your turn.** Do not wait on the worker: waiting is what blocks
  the chat.

## 2. Before each dispatch, compare files with what is running

- Different files: run it beside the others. Unrelated tasks have no limit of the kit's own; the
  tool's cap applies. The small worker count in `orchestrating-work` is for slices of one task,
  which share interfaces and have to be joined. It does not apply here.
- Overlapping files: queue the task behind the one that owns them, or give its worker a separate git
  worktree. Tell the user which you chose. Two workers never edit the same file in the same checkout.
- One delegation layer: workers do not start workers.

## 3. What a worker never does

Push, open or merge a pull request, tag, release, deploy, or delete outside the project. The user's
approval was given to you, in this chat, and does not travel. A worker that reaches such a step stops
and reports it. You carry it out yourself after checking the work, and only when the user has named it.

## 4. When a worker returns

1. Check its evidence yourself: read the diff and the check output. If the evidence is missing, run
   the narrowest check before you say anything. A worker's "done" is a claim until you have checked it.
2. Tell the user in a few lines: what changed, how it was verified, what is open.
3. Start any queued task that this one was blocking.

## 5. Status and updates

Keep the task list current and include it in every progress update. On Claude Code the kit's progress
hook wakes this chat every 8 minutes while workers run and names each one with its age. Codex and
Antigravity cannot wake an idle chat: say so once when the mode is turned on, and check on the workers
whenever the user next writes.
