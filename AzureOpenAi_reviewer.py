import os
import subprocess
from openai import AzureOpenAI
import re 
import sys

# 1. Configuration
API_KEY = os.environ.get("AZOpenAi_API_KEY")
AZURE_ENDPOINT = "https://LeadventureAIPOC.cognitiveservices.azure.com/"
AZURE_API_VERSION = "2024-05-01-preview"
AZURE_MODEL = "gpt-5-nano-2_Aadarsh"

# --- CORE PROMPT TEMPLATES: ENFORCING A STRICT STRUCTURE ---

# Strict instruction section used in both templates
STRICT_INSTRUCTION = """
If the code violates any standard, you MUST adhere to the following strict response format:
1. Start with the heading "### Violations".
2. List all findings clearly.
3. Immediately follow the findings with the heading "Corrected Version".
4. Provide the full corrected code snippet within a Markdown code block, using the correct language tag (e.g., csharp, typescript).

If the code is fully compliant, just reply 'CODE_COMPLIANT' and nothing else.
"""

# Template for C# files
CSHARP_PROMPT_TEMPLATE = f"""
You are a C# expert Code Reviewer. Review the following code snippet for adherence to these standards:
1. Naming conventions must be applied consistently: PascalCase for public members (classes, methods, properties), camelCase for local variables and method parameters, and private fields prefixed with an underscore.
2. Every public member must have XML documentation comments (///) that include at least a <summary> tag.
3. Code formatting must follow the Allman style for braces and use four-space indentation, with a maximum line length of 120 characters.
4. Use meaningful constants instead of magic numbers.

{STRICT_INSTRUCTION}
--- CODE SNIPPET TO REVIEW ---
{{code_snippet}}
--- END CODE SNIPPET ---
"""

# Template for TypeScript/JavaScript files
TS_JS_PROMPT_TEMPLATE = f"""
You are an expert TypeScript/Next.js Code Reviewer. Review the following code snippet for adherence to these standards:
1. Naming conventions must be applied consistently: camelCase for variables, functions, and methods; PascalCase for component names and class names.
2. Every public function/component must have JSDoc comments describing its purpose, parameters, and return value.
3. Use four-space indentation and avoid excessive nesting.
4. Use meaningful constants instead of magic numbers.

{STRICT_INSTRUCTION}
--- CODE SNIPPET TO REVIEW ---
{{code_snippet}}
--- END CODE SNIPPET ---
"""

# ----------------------------------------------------------------------
# CI/CD Helper Functions
# ----------------------------------------------------------------------

def get_changed_files():
    """Gets a list of changed files from the last commit."""
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD^', 'HEAD'],
            capture_output=True, text=True, check=True
        )
        changed_files = [
            f.strip() for f in result.stdout.splitlines()
            if f.strip().endswith(('.cs', '.ts', '.tsx', '.js', '.jsx'))
        ]
        return changed_files
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"Error running git diff: {e.stderr}\n")
        return []

def get_file_content(file_path):
    """Gets the entire content of a file at the current commit."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        sys.stderr.write(f"Warning: Could not read file {file_path}. Skipping. Error: {e}\n")
        return None

def get_language_prompt(file_path):
    """Returns the appropriate prompt template based on file extension."""
    if file_path.endswith('.cs'):
        return CSHARP_PROMPT_TEMPLATE
    elif file_path.endswith(('.ts', '.tsx', '.js', '.jsx')):
        return TS_JS_PROMPT_TEMPLATE
    return CSHARP_PROMPT_TEMPLATE # Default fallback

def review_code(file_path, code_content):
    """Calls the Azure OpenAI API for code review and returns the result text and usage metadata."""
    # Placeholder for usage metadata if API call fails or is skipped
    default_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    
    if not API_KEY:
        sys.stderr.write("AZOpenAi_API_KEY not found. Skipping review.\n")
        return "CODE_COMPLIANT", default_usage

    client = AzureOpenAI(
        api_key=API_KEY,
        api_version=AZURE_API_VERSION,
        azure_endpoint=AZURE_ENDPOINT
    )
    
    full_prompt = get_language_prompt(file_path).format(code_snippet=code_content)

    print(f"-> Sending {file_path} to Azure OpenAI for review...")
    
    try:
        response = client.chat.completions.create(
            model=AZURE_MODEL,
            messages=[
                {"role": "user", "content": full_prompt}
            ],
            reasoning_effort = "none",
            verbosity= "low"
            #temperature=0.2
        )
        content = response.choices[0].message.content
        # Extract usage data from the response
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens
        }
        return content.strip() if content else "", usage
    except Exception as e:
        sys.stderr.write(f"GENERAL ERROR for {file_path}: {e}\n")
        return f"GENERAL ERROR: Could not get review for {file_path}: {e}", default_usage

def generate_usage_report_artifact(artifact_dir, total_input_tokens, total_output_tokens, total_files_reviewed):
    """Creates a new artifact file with token consumption details."""
    report_filename = "token_usage_report.txt"
    report_path = os.path.join(artifact_dir, report_filename)
    
    total_tokens = total_input_tokens + total_output_tokens
    
    report_content = [
        "========================================\n",
        "      AZURE OPENAI TOKEN USAGE REPORT      \n",
        "========================================\n",
        f"Total Files Reviewed: {total_files_reviewed}\n",
        "----------------------------------------\n",
        f"TOTAL PROMPT (INPUT) TOKENS: {total_input_tokens}\n",
        f"TOTAL COMPLETION (OUTPUT) TOKENS: {total_output_tokens}\n",
        "----------------------------------------\n",
        f"GRAND TOTAL TOKENS CONSUMED: {total_tokens}\n",
        "========================================\n"
    ]

    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.writelines(report_content)
        print(f"\n📈 USAGE REPORT ARTIFACT CREATED:")
        print(f"   Download '{report_filename}' for token consumption details.")
    except Exception as e:
        sys.stderr.write(f"FATAL: Failed to write usage report artifact: {e}\n")

# ----------------------------------------------------------------------
# Main Execution Logic
# ----------------------------------------------------------------------

def main():
    print("--- Starting Azure OpenAI Code Review Pipeline ---")
    
    violations_found = False
    all_raw_responses_content = [] # Initialize list to store all raw responses
    
    # Initialize token counters
    total_input_tokens = 0
    total_output_tokens = 0
    total_files_reviewed = 0
    
    # 1. Prepare Artifact Directory
    artifact_dir = "corrected_code_artifacts"
    os.makedirs(artifact_dir, exist_ok=True)
    print(f"Artifacts will be saved to: {artifact_dir}. Look for the **Artifacts** tab on this build page.")
    
    # 2. Get changed files
    changed_files = get_changed_files()
    if not changed_files:
        print("No relevant code files changed. Pipeline step successful.")
        return
    
    print(f"Files to review: {', '.join(changed_files)}")
    
    # Define regex patterns globally for re-use
    # Pattern to find all content between '### Violations' and 'Corrected Version'
    VIOLATIONS_PATTERN = re.compile(r'###\s*Violations\s*\n*(.*?)\s*(?:Corrected Version|\Z)', re.DOTALL | re.IGNORECASE)
    # Pattern to find the content inside any markdown code block (```[lang]\n...\n```) following 'Corrected Version'
    CODE_PATTERN = re.compile(r'(?:Corrected Version).*?```[\w\s]*\n(.*?)\n```', re.DOTALL | re.IGNORECASE)

    for file_path in changed_files:
        code_content = get_file_content(file_path)
        if not code_content:
            continue
            
        review_result, usage_metadata = review_code(file_path, code_content)
        
        # Aggregate token usage
        total_input_tokens += usage_metadata.get("prompt_tokens", 0)
        total_output_tokens += usage_metadata.get("completion_tokens", 0)
        total_files_reviewed += 1
        
        # --- AGGREGATE RAW RESPONSE (Updated to include usage) ---
        all_raw_responses_content.append(f"\n\n========================================\n")
        all_raw_responses_content.append(f"RAW AZURE OPENAI RESPONSE FOR FILE: {file_path}\n")
        # Include token usage in the raw response artifact for individual file tracking
        all_raw_responses_content.append(f"  USAGE: Input Tokens={usage_metadata.get('prompt_tokens', 0)}, Output Tokens={usage_metadata.get('completion_tokens', 0)}\n")
        all_raw_responses_content.append(f"========================================\n")
        all_raw_responses_content.append(review_result)
        # --- END AGGREGATE RAW RESPONSE ---

        if "CODE_COMPLIANT" in review_result:
            print(f"✅ PASSED: {file_path} is compliant.")
        else:
            violations_found = True
            
            # --- Artifact Generation Logic ---
            
            # 1. Extract Violations Section
            violations_match = VIOLATIONS_PATTERN.search(review_result)
            violations_section = violations_match.group(1).strip() if violations_match else None
            
            # 2. Extract Corrected Code
            code_match = CODE_PATTERN.search(review_result)
            corrected_code = code_match.group(1).strip() if code_match else None
            
            # 3. Print the clean report
            print(f"\n❌ VIOLATION FOUND in {file_path}:")
            print("=" * 40)
            
            if violations_section:
                print(violations_section)
            else:
                # Fallback print if structured parsing failed for violations
                print("⚠️ ERROR: Could not parse violations section. Check the raw response artifact.")
                
            print("=" * 40)

            # 4. Save corrected code as an artifact file
            if corrected_code:
                # Create a file name based on the original path and the correct extension
                base_name, ext = os.path.splitext(os.path.basename(file_path))
                artifact_filename = f"{base_name}_corrected{ext}"
                artifact_path = os.path.join(artifact_dir, artifact_filename)

                try:
                    with open(artifact_path, 'w', encoding='utf-8') as f:
                        f.write(corrected_code)
                        
                    # 5. Print the instruction message 
                    print(f"🛠️ **CORRECTED CODE AVAILABLE AS ARTIFACT**:")
                    print(f"   Download '{artifact_filename}' from the **Artifacts** tab to view the suggested fix.")
                    print("-" * 40)
                except Exception as e:
                    sys.stderr.write(f"⚠️ Failed to write artifact file {artifact_filename}: {e}\n")
            else:
                # Final failure message if code extraction failed
                print("⚠️ ERROR: Could not parse the corrected code block after the 'Corrected Version' header.")
                print("   **ACTION REQUIRED:** Check the raw response artifact for the API's full output.")
                print("-" * 40)

    # 6. Write the single, aggregated raw response file
    raw_artifact_path = os.path.join(artifact_dir, "all_raw_responses.txt")
    if all_raw_responses_content:
        try:
            with open(raw_artifact_path, 'w', encoding='utf-8') as f:
                f.writelines(all_raw_responses_content)
            print(f"\n\n--- Debug Artifact Created ---\n")
            print(f"A single file containing all raw API responses has been saved as 'all_raw_responses.txt'.")
        except Exception as e:
            sys.stderr.write(f"FATAL: Failed to write aggregated raw response artifact: {e}\n")

    # 7. Generate Token Usage Report
    generate_usage_report_artifact(artifact_dir, total_input_tokens, total_output_tokens, total_files_reviewed)

    # 8. Enforce Failure
    if violations_found:
        print("\n--- CODE STANDARD VIOLATIONS DETECTED. FAILING BUILD. ---")
        exit(1)
    else:
        print("\n--- All reviewed code is compliant. Pipeline step successful. ---")
        sys.exit(0)

if __name__ == "__main__":
    main()
