# StockSight hosted AI coach

This Appwrite Function keeps the NVIDIA NIM key on the server. The Windows EXE sends the signed-in user's chat request to Appwrite, and Appwrite calls NVIDIA without exposing the key to the user.

## Create the Function

1. In Appwrite, open **Functions** and choose **Create function**.
2. Use the name **StockSight AI Coach** and Function ID `stocksight_ai_coach`.
3. Select the **Node.js 22** runtime.
4. Upload a `.tar.gz` archive containing this folder's `package.json` and `src/main.js` at the archive root.
5. Set the entrypoint to `src/main.js` and use `npm install` as the build command.
6. Under **Execute access**, grant access to **Users**. Do not grant **Any** or **Guests** access.

## Add the NVIDIA key safely

In the Function's **Settings** > **Environment variables**:

1. Create a variable named `NVIDIA_NIM_API_KEY`.
2. Paste a newly created NVIDIA key.
3. Turn on **Secret**.
4. Redeploy the Function.

The key must never be placed in the EXE, a repository file, Vercel, or a screenshot. Appwrite requires a redeploy after changing function variables for the new value to take effect.

## v2 behavior

Ordinary Flow chat uses a fast response. StockSight Pro research briefs use the
same hosted model with reasoning enabled and a larger response budget. The
desktop cannot choose a different model: the Function keeps that decision on
the server.

## Connect the EXE

After the Function deployment succeeds, copy the Function ID and set it in the build environment as:

```text
APPWRITE_AI_FUNCTION_ID=stocksight_ai_coach
```

Build and publish a new StockSight Learner EXE. Signed-in users will then see **Hosted NVIDIA AI Coach** in AI Chat. If the function is unavailable, the built-in learning coach remains available.
