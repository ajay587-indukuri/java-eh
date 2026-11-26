# EH — Java Exception Playground

A small Flask app for running Java snippets and showing the program output with a short explanation for recognized exceptions.

## Run locally

Install Python 3.11+ and a JDK, then run:

```bash
python -m pip install -r requirements.txt
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). Local runs use the JDK installed on your machine and are intended for local development.

## Deploy to Vercel

Production execution uses a fresh Vercel Sandbox per run. Submitted Java runs with network access disabled, no application environment variables, one virtual CPU, a 2 GB memory ceiling, a 10-second process limit, and bounded source/output sizes.

1. Link this directory to a Vercel project and pull its local development credentials:

   ```bash
   npx vercel@latest login
   npx vercel@latest link
   npx vercel@latest env pull .env.local
   ```

2. Build a reusable Java 17 sandbox snapshot:

   ```bash
   python -m pip install -r requirements.txt
   python build_java_snapshot.py
   ```

   Copy the printed `JAVA_SNAPSHOT_ID` into the Vercel project's Development, Preview, and Production environments.

3. Deploy:

   ```bash
   npx vercel@latest --prod
   ```

The snapshot builder installs Java only in a trusted, disposable sandbox, disables its network before saving the snapshot, and does not add credentials or sandbox contents to this repository. Refresh the snapshot periodically to pick up Java and operating-system security updates.

## Limits

The public `/run` endpoint accepts up to 30,000 source characters. Sandbox compilation and execution are each limited to 10 seconds, and returned output is capped. Vercel Sandbox usage is subject to the limits and pricing of the linked Vercel account.

This demo has no application-level request rate limit. Configure Vercel Firewall protections before sharing it widely, since repeated runs consume Sandbox quota.
