# StockSight Learner

![StockSight Learner preview](public/og.png)

A clear, beginner-friendly download page for the StockSight Learner Windows desktop app.

The page explains the product, provides Windows installation guidance, links visitors to the current Gofile release, and includes a SHA-256 verification area. It is intentionally educational and does not make investment recommendations or performance promises.

## What visitors see

- Product overview for beginning investors
- Prominent Windows download link
- Release version and file-size details
- Three-step installation guide
- Windows security-warning guidance
- Optional SHA-256 verification and one-click copy action
- Support link and educational-risk disclaimer

## Publish a release

Set these values in **Vercel → Project Settings → Environment Variables** before deploying:

| Variable | Purpose |
| --- | --- |
| `VITE_DOWNLOAD_URL` | Public `https://gofile.io/...` release URL |
| `VITE_RELEASE_VERSION` | Release label shown on the page |
| `VITE_FILE_SIZE` | Download size shown on the page |
| `VITE_SHA256` | 64-character SHA-256 checksum for the EXE |

The page safely hides all download buttons until it receives a valid Gofile URL.

## Deploy with Vercel

1. Import this GitHub repository into Vercel.
2. Add the four release variables above.
3. Deploy. Every future push to `main` will trigger a new deployment.

## Local development

```bash
npm install
npm run dev
```

## Support

For installation help, contact [kian.jindal2010@gmail.com](mailto:kian.jindal2010@gmail.com).
