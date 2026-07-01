# FitBrain — coaching layer

`fitbrain_system_prompt.md` turns a Claude Project (or any assistant with the
`fitness` MCP server attached) into a data-driven fitness coach that always
pulls fresh data before answering.

## Setup (Claude Desktop / claude.ai Projects)

1. Make sure the `fitness` MCP server is connected (see the repo README —
   `scripts/claude_config.py --write`).
2. Create a new **Project** named `FitBrain`.
3. Paste the contents of [`fitbrain_system_prompt.md`](fitbrain_system_prompt.md)
   into the Project's **custom instructions**.
4. Edit the "Who I am" and "Goals" sections to match you.

## Example questions

- "Check my data freshness, then summarize the last 4 weeks of training."
- "Correlate my sleep score with HRV over the last 3 months — is there a signal?"
- "What's my recovery status today, and should I do a hard session?"
- "Show my weekly running volume and elevation trend — am I on track for a 44 km
  trail marathon?"
- "Any overtraining signals in the last 2 weeks? Look at load spikes, HRV, and
  sleep."
- "Has my bodyweight moved with training volume this quarter?"
- "What are my running personal bests, and when did I set them?"

## Tip

If you haven't synced recently, either ask FitBrain to sync (it can call
`fitness_sync`) or run a manual/scheduled sync first (see the repo README's
"Recurring (automated) sync").
