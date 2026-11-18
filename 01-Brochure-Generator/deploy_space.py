"""
Deploy this app to a Hugging Face Space (free hosting for a live demo).

Only the files listed in FILES are uploaded, so your .env (API keys) and the
outputs/ folder can never end up on the Space.

One-time setup:
    hf auth login        # paste a Hugging Face token with "write" access

Deploy (run again after every change):
    python deploy_space.py your-username/ai-brochure-generator
    python deploy_space.py your-username/ai-brochure-generator --dry-run   # only list the files

After the first deploy, open the Space -> Settings -> Variables and secrets ->
New secret: name GROQ_API_KEY, value = your Groq key. Hugging Face keeps it on
its servers; it never appears in the code and visitors can't see it.
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (file in this folder, path on the Space)
FILES = [
    ("space_card.md", "README.md"),       # Space settings (YAML header) + description
    ("app.py", "app.py"),
    ("requirements.txt", "requirements.txt"),
    ("packages.txt", "packages.txt"),     # fonts for Hindi / Chinese / Japanese / Korean PDFs
    *[(f"brochure/{p.name}", f"brochure/{p.name}") for p in sorted((HERE / "brochure").glob("*.py"))],
]


def main():
    parser = argparse.ArgumentParser(description="Deploy the Brochure Generator to a Hugging Face Space")
    parser.add_argument("space", help="Space id, e.g. your-username/ai-brochure-generator")
    parser.add_argument("--dry-run", action="store_true", help="Only list the files that would be uploaded")
    parser.add_argument("--private", action="store_true", help="Create the Space as private (default: public)")
    args = parser.parse_args()

    if args.space.count("/") != 1:
        sys.exit("Use the form your-username/space-name")
    missing = [local for local, _ in FILES if not (HERE / local).exists()]
    if missing:
        sys.exit(f"Missing files: {', '.join(missing)}")

    print(f"Files for https://huggingface.co/spaces/{args.space}:")
    for local, remote in FILES:
        print(f"  {local:28} -> {remote}")
    if args.dry_run:
        return

    from huggingface_hub import CommitOperationAdd, HfApi

    api = HfApi()
    try:
        user = api.whoami()["name"]
    except Exception:
        sys.exit("Not logged in to Hugging Face. Run `hf auth login` first (token with write access).")
    print(f"Logged in as {user}")

    api.create_repo(args.space, repo_type="space", space_sdk="gradio", private=args.private, exist_ok=True)
    operations = [CommitOperationAdd(path_in_repo=remote, path_or_fileobj=str(HERE / local))
                  for local, remote in FILES]
    api.create_commit(args.space, repo_type="space", operations=operations,
                      commit_message="Deploy AI Company Brochure Generator")

    extra = set(api.list_repo_files(args.space, repo_type="space")) - {r for _, r in FILES} - {".gitattributes"}
    if extra:
        print(f"Note: the Space also has files this script didn't upload: {', '.join(sorted(extra))}")
    print(f"\nDeployed: https://huggingface.co/spaces/{args.space}")
    print("It takes a few minutes to build. If you haven't yet, add the secret GROQ_API_KEY under "
          "Settings -> Variables and secrets.")


if __name__ == "__main__":
    main()
