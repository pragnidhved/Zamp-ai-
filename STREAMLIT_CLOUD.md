# Streamlit Community Cloud version

The Streamlit entrypoint is the repository-root file `streamlit_app.py`. It calls the existing PDF extraction, parsing, and reconciliation services directly. Community Cloud installs Python packages from root `requirements.txt` and Tesseract from root `packages.txt`.

## Data handling

This is a public-demo design, not a production AP system. Every browser session gets its own in-memory SQLite database seeded with demo vendors and POs. Uploaded PDFs are written to a temporary directory only while the extractor reads them, then removed. Parsed fields, decisions, PO balance changes, and any human review remain in that browser session's memory and are cleared when the session ends or the app restarts. Different browser sessions do not share invoice records. The app displays a reminder not to upload confidential or regulated invoices because the PDF is transmitted to the Streamlit host for processing.

The existing local FastAPI/React version remains available and continues using its local persistent SQLite database. Its database and uploaded files are excluded by `.gitignore`; do not add them to the GitHub repository.

## Deploy

1. Put the project source in a GitHub repository. Do not commit `backend/data/*.db`, `backend/uploads/`, virtual environments, or real invoice PDFs.
2. Sign in at [Streamlit Community Cloud](https://share.streamlit.io/) with GitHub and choose **Create app**.
3. Select the repository, branch, and root entrypoint `streamlit_app.py`.
4. Choose Python 3.12 in Advanced settings (Community Cloud's current default is also 3.12) and deploy.
5. Keep the app private if you don't intend to share it. A public app can be viewed by anyone; this demo has no user login.

Streamlit Community Cloud deploys from GitHub and reads Python dependencies from `requirements.txt` and Linux packages from `packages.txt`. See [Streamlit's deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) and [dependency guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies).

## Run locally

From the project root in PowerShell:

```powershell
backend\.venv\Scripts\python.exe -m pip install -r requirements.txt
backend\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

The Streamlit URL will be printed in the terminal, usually `http://localhost:8501`.
