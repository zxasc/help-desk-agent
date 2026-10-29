## Installation

I recommend using [uv](https://docs.astral.sh/uv/) to install the CLI.

```sh
git clone https://github.com/zxasc/help-desk-agent.git help_desk_agent
cd help_desk_agent
uv tool install .
# ... or install without cloning the repo:
uv tool install git+https://github.com/zxasc/help-desk-agent
```

## Running

You can use any OpenAI-compatible API with the ability to do tool calls. Set up your `.env` file first:

```dotenv
LLM_API_URL=https://your.api/v1
LLM_API_KEY=sup3r-s3cr3t-k3y
LLM_MODEL=provider/your-favorite-model
```

Remember to start API server if using local model:

```sh
llama serve -hf provider/your-favorite-model --jinja
```

Running the CLI:

```sh
help_desk_agent check-health  # check your .env and API connection first
help_desk_agent ask "How much do I get back if I cancel CW-1002?"
help_desk_agent ask "..." -v  # also show which tools ran
help_desk_agent ask "..." -vv  # also show tool arguments and results
help_desk_agent --log-level debug ask "..."  # full requests and response logs
```

## Testing

The tests need no network and no API key. You have to clone the repo in order to run tests.

```sh
uvx --with tox-uv tox  # run ruff, mypy and full test suite
uvx --with tox-uv tox -e test  # run tests only
```

You can also run the evaluation suite with your model.

```sh
help_desk_agent evaluate
```

## Providers and models

I tried three providers:

1. **Google Gemini, `gemini-3.8-flash`**. This was my first choice, as I knew its API was
   OpenAI-compatible, and that it had a free tier. I managed to get it working only once, on my
   first try. Google's API started returning 503 afterwards, and after a few minutes I've manageged
   to hit their rate limit.
2. **AionLabs, `aion-2.0`**. To be honest, I've never heard of AionLabs prior to googling "free llm API".
   I did not stick to it for long, because of a 20k daily token limit, which I've hit in 3 minutes
   of usage.
3. **Qwen 3 8B**. I decided not to try my luck for the third time, and I've decided to use something
   I knew was both reliable and free. I hosted a quantized version of this model on my Mac Mini M4
   16gb. It turned out to be *relatively* fast, or rather fast enough. It had no rate limit, so I
   could run evaluation as often as I wanted.


## How the agent works

The code lives in `src/help_desk_agent/`:

- `cli.py`: `click` command-line interface.
- `agent.py`: the agent loop and the system prompt.
- `llm_client.py`: class for communicating with provider API.
- `tools.py`: tools module.
- `core.py`: data classes common to other modules.
- `evaluation.py`: the evaluation logic.

### Loop

1. The agent sends the system prompt, user's question and the tool definitions to the model.
2. If the reply contains tool calls, the agent runs each tool, adds each result to the conversation
   as a `tool` message linked to its call, and asks the model again.
3. If the reply has no tool calls, its text is the final answer.
4. After `--max-steps` rounds without a final answer, the agent stops with a message saying so.

The agent never crashes: an unknown tool name, invalid JSON arguments or wrong argument names go
back to the model as an error message, so it can correct itself.

### Tools

- **`search_policies(query)`** splits each Markdown file in `data/policies/` into its header sections
  and ranks them by the words they share with the query, ignoring certain common words. A match in
  a section heading counts double. Words match on their first 5 letters, so "cancel", "cancelled"
  and "cancellation" match each other. It then returns the 3 best sections with file and heading,
  or "No matching policy found."
- **`get_booking(booking_id)`** returns the booking from `data/bookings.json`. If a booking does not
  exist, it return an error.
- **`calculate_refund(booking_id)`** does all the money calculation in code, per rules from the task:
  - only confirmed bookings can be cancelled; others return `can_cancel: false` and 0;
  - 48 hours or more before the start: 100% of the rental; 24 to 48 hours: 50%; less than 24 hours: 0%;
  - the booking fee is never refunded; the deposit is always refunded in full;
  - card payments go back to the card within 5 working days, voucher payments come back as a new voucher.

### Instructions

The system prompt gives the model a role of a CityWheels help desk person and the following rules:

1. Answer only from tool results, never from general knowledge.
2. For shop information, call `search_policies` first.
3. For a booking, call `get_booking`. If it's not found, say so.
4. Never calculate refunds yourself, use `calculate_refund` tool and repeat its amounts exactly.
5. Never make up booking details, amounts, dates or rules.
6. If the tools do not answer the question, or it is not about CityWheels, don't answer it,
   instead call `search_policies` tool to find the contact details and give them to the user.
7. Answer in the user's language, short and concrete.

### Tests

- `tests/tools/`: unit tests for tools.
- `tests/test_agent.py`: tests of the agent loop with a fake model that returns scripted replies,
  covering tool calls, unknown tools, invalid arguments and the step limit.
- `tests/test_evaluation.py`: tests of the evaluation checks.

## Evaluation results

`eval/questions.toml` has 15 questions:

- 4 about policies,
- 2 about bookings,
- 6 about refunds,
- 3 that the agent should refuse or pass to the staff.

Each question lists its own checks:

- tools that must or must not be called,
- numbers that must or must not appear,
- phrases that must or must not appear.

My latest evaluation passed with score **15/15**. Qwen 3 8B always correctly answers all 15
questions, consistently.

This was not the case during development though. Previously I've had some problems with
fake-negatives, when questions were too strict.

## AI Coding

I used Claude Code to pair programm with it. I used it mostly to generate code, which I've then 
manually reviewed. I often had to ask it to explain its choices, and often found simpler ways to
implement certain details. A few examples of AI-generated code, which I had to fix:

- **The first agent loop threw away answers.** The first version asked the model to reply in a text
  format (`Thought:` / `Action:` lines) and parsed it. When the model answered in normal text,
  the parser threw the reply away, and the CLI showed an empty answer. I noticed because the debug
  logs showed the provider did return text. I switched to the provider's native tool calling,
  which removed the parser completely.
- **Retries without a pause.** The client was supposed to retry HTTP 503 errors, but it sent 3
  requests within one second and gave up. I noticed in the logs. Now retries wait longer each time.

## Limitations

- **No conversation memory.** Every `ask` is a new conversation, so no follow-up questions.
- **Simple search.** `search_policies` matches words, not meaning. It does not know synonyms. It
  works only for English.

## Further development

- Add conversation memory.
- Make code easily 
- Evaluate different models multiple times.
- Add a second evaluation using another model as a judge.
- Write a better version of `search_policies`.
- Make the code more extensible by adding ports/connectors layers.
