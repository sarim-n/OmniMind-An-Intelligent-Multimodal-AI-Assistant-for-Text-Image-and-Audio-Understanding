import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..");
const openapiPath = path.join(rootDir, "openapi.json");
const outputPath = path.join(rootDir, "src", "api", "types.ts");

async function main() {
  let jsonText = "";

  // 1. Try fetching from live backend
  try {
    const res = await fetch("http://127.0.0.1:8000/openapi.json", { signal: AbortSignal.timeout(1500) });
    if (res.ok) {
      jsonText = await res.text();
      console.log("Fetched openapi.json from live backend at http://127.0.0.1:8000");
    }
  } catch {
    // Backend not running, proceed to export from Python
  }

  // 2. If not live, try python export
  if (!jsonText) {
    const backendDir = path.resolve(rootDir, "..", "backend");
    const venvPythonWin = path.join(backendDir, ".venv", "Scripts", "python.exe");
    const pythonExe = fs.existsSync(venvPythonWin) ? `"${venvPythonWin}"` : "python";

    try {
      console.log("Generating openapi.json using backend python...");
      const pyCmd = `${pythonExe} -c "import sys, json, pathlib; sys.path.insert(0, '${backendDir.replace(/\\/g, "/")}'); from app.main import app; pathlib.Path('${openapiPath.replace(/\\/g, "/")}').write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')"`;
      execSync(pyCmd, { stdio: "inherit" });
    } catch (e) {
      if (!fs.existsSync(openapiPath)) {
        console.error("Failed to generate openapi.json:", e);
        process.exit(1);
      }
      console.log("Using existing openapi.json fallback");
    }
  } else {
    fs.writeFileSync(openapiPath, jsonText, "utf-8");
  }

  // 3. Run openapi-typescript
  console.log("Running openapi-typescript...");
  execSync(`npx openapi-typescript "${openapiPath}" -o "${outputPath}"`, {
    cwd: rootDir,
    stdio: "inherit",
  });
  console.log("API types generated successfully at src/api/types.ts");
}

main().catch((err) => {
  console.error("gen:api failed:", err);
  process.exit(1);
});
