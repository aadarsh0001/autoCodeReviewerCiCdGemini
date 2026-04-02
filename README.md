For further details, check the individual READMEs.

## Azure OpenAI Code Review Pipeline

This repository also includes an automated code-review pipeline powered by Azure OpenAI.

- Pipeline file: `bitbucket-pipelines.yml`
- Reviewer script: `AzureOpenAI_reviewer.py`

### How it runs

- Bitbucket pipeline installs dependency: `openai`
- Pipeline executes: `python AzureOpenAI_reviewer.py`
- Script reviews changed files from the last commit (`HEAD^` to `HEAD`) for these extensions:
  - `.cs`, `.ts`, `.tsx`, `.js`, `.jsx`
- Artifacts are written under: `corrected_code_artifacts/**`

### Configuration source (no hardcoded secrets)

All Azure OpenAI runtime values are read from Bitbucket Repository Variables using `os.environ.get(...)` in `AzureOpenAI_reviewer.py`.

Required variables:

- `AZOpenAi_API_KEY`
- `AZOpenAi_ENDPOINT`
- `AZOpenAi_API_VERSION`
- `AZOpenAi_MODEL`

Mapping in script:

- `API_KEY = os.environ.get("AZOpenAi_API_KEY")`
- `AZURE_ENDPOINT = os.environ.get("AZOpenAi_ENDPOINT")`
- `AZURE_API_VERSION = os.environ.get("AZOpenAi_API_VERSION")`
- `AZURE_MODEL = os.environ.get("AZOpenAi_MODEL")`

If any required value is missing, the script logs a clear configuration message and skips the review call safely.

### Response control settings

Inside the Azure OpenAI chat completion request, these options are set:

- `reasoning_effort="none"`
- `verbosity="low"`

Purpose:

- Keep responses compact and focused on the strict review format.
- Reduce extra reasoning text and output noise.

Note:

- `temperature` is currently not used in this script for the selected model configuration.

### Usage reporting

The script captures token usage from Azure OpenAI response metadata:

- `prompt_tokens`
- `completion_tokens`

It generates:

- `corrected_code_artifacts/token_usage_report.txt`
- `corrected_code_artifacts/all_raw_responses.txt`

If violations are found, corrected suggestions are saved as per-file artifacts in the same directory.
