# Model Regression Detection System

An evaluation harness and lightweight Gmail mail summarizer for testing prompt and model changes. The project classifies emails, generates concise summaries, evaluates those summaries against a hand-written golden dataset, and compares evaluation runs to detect regressions.

## What It Does

The system has two related workflows:

1. **Evaluation:** Run the classifier and an LLM judge against the cases in `golden_dataset.yaml`.
2. **Production mail summary:** Read new unread messages from the Gmail Primary category and print a category and summary for each message.

The evaluation workflow is the release gate for prompt changes. A prompt version should be validated with `run_eval.py` before it is selected by `main.py`.

## Project Layout

| Path | Purpose |
| --- | --- |
| `classifier.py` | Loads prompts, calls the configured OpenAI-compatible model, validates JSON responses, and judges summaries. |
| `main.py` | Production Gmail workflow. Fetches up to two new unread Primary messages and classifies them. |
| `run_eval.py` | Runs the classifier and judge against the golden dataset and saves a detailed YAML result. |
| `compare_runs.py` | Compares two evaluation runs, reports metric changes and case-level flips, and optionally sends a Slack alert. |
| `prompts/v1.yaml` | Prompt version 1. |
| `prompts/v2.yaml` | Prompt version 2 with explicit categories and more detailed summary rules. |
| `prompts/v3.yaml` | Prompt version 3, a shorter version of the classification rules. |
| `golden_dataset.yaml` | Hand-written evaluation cases and expected outcomes. |
| `eval_results/` | Generated YAML records from evaluation runs. |
| `credentials.json` | Local Google OAuth client credentials. Ignored by Git and required only for Gmail access. |
| `token.json` | Local OAuth refresh/access token generated after the first Gmail login. Ignored by Git. |
| `processed_ids.json` | Local set of Gmail message IDs already processed by `main.py`. Ignored by Git. |

## Requirements

- Python 3.10 or newer
- A Google Cloud project with the Gmail API enabled, if using `main.py`
- An OpenAI-compatible chat completions endpoint
- An API key and model supported by that endpoint

The required Python packages are listed in `requirements.txt`.

## Installation

Create and activate a virtual environment, then install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

## Configuration

Create a `.env` file in the repository root. It must contain:

```dotenv
AI_API_KEY=your-api-key
AI_BASE_URL=https://your-openai-compatible-endpoint/v1
MODEL=your-model-name
```

`AI_BASE_URL` and `MODEL` are required by both the evaluation and production workflows. `SLACK_WEBHOOK_URL` is optional and is used only by `compare_runs.py`:

```dotenv
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

For WhatsApp delivery from `main.py`, configure the WhatsApp Cloud API and add these values to `.env`:

```dotenv
WHATSAPP_PHONE_NUMBER_ID=your-meta-phone-number-id
WHATSAPP_ACCESS_TOKEN=your-meta-access-token
WHATSAPP_TO=15551234567
```

`WHATSAPP_TO` must be the recipient's phone number in international format, without `+`, spaces, or punctuation. The recipient must have an active conversation with the business number, or the Cloud API must use an approved message template when initiating a conversation outside the 24-hour customer-service window.

### Gmail OAuth setup

To use `main.py`:

1. Create or select a project in Google Cloud Console.
2. Enable the Gmail API.
3. Configure the OAuth consent screen.
4. Create an OAuth client of type **Desktop app**.
5. Download the client JSON and save it as `credentials.json` in the repository root.
6. Run `python main.py` and complete the browser authorization flow.

The first successful authorization creates `token.json`. The application requests the read-only Gmail scope `https://www.googleapis.com/auth/gmail.readonly`. Both OAuth files are local secrets and are ignored by Git.

## Run an Evaluation

Run the default prompt version, `v1`:

```bash
python run_eval.py
```

Choose a prompt version explicitly:

```bash
python run_eval.py v2
python run_eval.py v3
```

For each active case, the script:

1. Calls the classifier to produce a category and summary.
2. Checks the category against `expected_category`.
3. Checks whether every string in `expected_facts` appears in the summary, case-insensitively.
4. Calls the LLM judge to check whether the summary is accurate and sufficiently specific.
5. Marks the case as an overall pass only when category, judge, and fact coverage all pass.

The complete result is printed and saved to `eval_results/YYYYMMDDTHHMMSS_<prompt_version>.yaml`. Evaluation calls retry transient or malformed responses before recording an error for a case.

The final report includes:

- Overall pass rate
- Category accuracy
- Judge accuracy
- Fact coverage
- Total and average token use
- Evaluation duration
- IDs of failed cases

## Compare Evaluation Runs

After at least two result files exist, compare the two most recent runs:

```bash
python compare_runs.py
```

Or compare the latest saved run for two prompt versions explicitly. The first argument is the current version and the second is the previous version:

```bash
python compare_runs.py v2 v1
python compare_runs.py v3 v2
```

The comparison reports changes in:

- `overall_pass_rate`
- `category_accuracy`
- `judge_accuracy`
- `fact_coverage`
- Average tokens per case

It also lists individual cases that changed from pass to fail or fail to pass.

Regression thresholds are percentage-point changes:

- **No significant change:** less than 3 points in either direction
- **Warning:** a decrease of at least 3 points
- **Critical regression:** a decrease of at least 8 points

If `SLACK_WEBHOOK_URL` is configured, the same comparison summary is sent to Slack. Without it, the comparison still runs and prints a notice that the alert was skipped.

## Run the Production Gmail Summarizer

Once Gmail OAuth and the AI settings are configured:

```bash
python main.py
```

To resend currently unread messages that are already in `processed_ids.json`,
use:

```bash
python main.py --resend
```

The workflow:

1. Loads the selected prompt version, currently `v3` in `main.py`.
2. Finds up to two messages matching `is:unread category:primary`.
3. Skips message IDs already present in `processed_ids.json`.
4. Extracts the plain-text body, subject, sender, and timestamp.
5. Classifies messages and sends each category and summary to WhatsApp, including the sender and subject.
6. Records a message ID only after its WhatsApp delivery succeeds.

The Gmail message body sent to the classifier is limited to the first 3,000 characters. If there are no new matching messages, the command prints `No new unread mail.`

To promote a validated prompt, update `PROMPT_VERSION` in `main.py`, then run the evaluation for that version before running the production workflow.

## Docker Deployment

Build and export the image locally:

```bash
docker build -t model-regression-whatsapp:latest .
docker save model-regression-whatsapp:latest | gzip > model-regression-whatsapp.tar.gz
```

Copy these files to the server:

- `model-regression-whatsapp.tar.gz`
- `docker-compose.yml`
- `.env`
- `credentials.json`
- `token.json`
- `processed_ids.json` (create it with `echo '[]' > processed_ids.json` if missing)

On the server, load and start the listener:

```bash
gunzip -c model-regression-whatsapp.tar.gz | docker load
docker-compose up -d
docker-compose logs -f email-whatsapp-listener
```

The container polls Gmail every 30 seconds by default and sends each newly seen unread Primary email directly to WhatsApp. Set `POLL_INTERVAL_SECONDS` in `.env` to change the interval. Stop it with `docker-compose down`; it restarts automatically after a server reboot.

## Prompt and Dataset Format

Each prompt file is YAML with a version and system prompt:

```yaml
version: v3
system_prompt: |
  Classify this email...
```

Each active golden case contains an ID, email fields, an expected category, a difficulty label, and optional keyword facts:

```yaml
- id: case_example
  subject: "Example subject"
  sender: "sender@example.com"
  body: "Example email body."
  expected_category: Work
  difficulty: easy
  expected_facts: ["Example", "subject"]
```

`expected_facts` are literal substring checks, not semantic matching. Keep them concrete and stable so changes in wording do not make the evaluation unnecessarily brittle. Cases can be temporarily disabled by commenting out the complete YAML item.

## Model Response Contract

The classifier must return a JSON object containing non-empty string fields:

```json
{
  "category": "Work",
  "summary": "The email asks for the Q3 report by Friday."
}
```

The judge must return:

```json
{
  "verdict": "pass",
  "reason": "The summary accurately represents the email."
}
```

Invalid JSON, empty required fields, and judge verdicts other than `pass` or `fail` are treated as errors.

## Security and Repository Hygiene

Do not commit any of the following:

- `credentials.json`
- `token.json`
- `.env`
- `processed_ids.json`
- Slack webhook URLs or AI API keys

These local files are listed in `.gitignore`. If a credential has ever been committed or exposed, revoke or rotate it at the provider immediately; adding it to `.gitignore` does not remove it from existing Git history.

## Troubleshooting

**`Set AI_API_KEY and AI_BASE_URL ...`**

Check that `.env` is in the repository root, uses the exact variable names, and is loaded before running the command.

**`Set MODEL as an environment variable ...`**

Add `MODEL` to `.env` and use a model name accepted by the configured endpoint.

**Gmail authorization errors**

Confirm that the Gmail API is enabled, the OAuth client is a Desktop app client, and `credentials.json` is the downloaded client configuration rather than an access token. Delete an invalid local `token.json` and authorize again if necessary.

**`Need at least 2 runs ...`**

Run `python run_eval.py v1` and another evaluation, such as `python run_eval.py v2`, before comparing.

**A case fails fact coverage**

Inspect `facts_missing` and `actual_summary` in the saved result. Fact coverage uses case-insensitive literal substrings, so a semantically equivalent phrase may still fail.

## Development Notes

There is currently no automated unit-test suite in the repository. The golden-dataset evaluation is the primary behavioral check. When changing classifier logic or prompt behavior, run the relevant evaluation and compare it with the previous result before promoting the change.