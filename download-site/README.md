# StockSight Learner download site

This is the standalone Vercel landing page for the Windows desktop release.

## Publish a release

1. Upload `../dist/StockSightLearner-Updated.exe` to Gofile and copy its public HTTPS URL.
2. Copy `.env.example` to `.env` and set the release values:
   - `VITE_DOWNLOAD_URL` must be an `https://gofile.io/...` link.
   - `VITE_RELEASE_VERSION` is the label shown on the page.
   - `VITE_FILE_SIZE` is the download size shown on the page.
   - `VITE_SHA256` must be the 64-character SHA-256 value of the uploaded EXE.
3. In Vercel, import the `download-site` folder as a new project and add the same four variables under **Project Settings → Environment Variables**.
4. Deploy. Vercel will provide the permanent `*.vercel.app` address.

The page deliberately hides every download button if the configured Gofile URL is missing or not valid. It shows the checksum only when it is a valid SHA-256 value.

## Local preview

Install dependencies with `npm install`, then use `npm run dev`.
