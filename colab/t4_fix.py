"""Fix ACE-Step 1.5 "NaN or Inf latents" on pre-Ampere GPUs (Colab T4).

ACE-Step runs in float16 on GPUs without bfloat16 (compute capability < 8),
which can overflow and produce NaN latents. This script:
  1. patches ACE-Step to use float32 on those GPUs (DiT + VAE),
  2. restarts `acestep-api` with the 5Hz LM disabled to save GPU memory,
  3. waits until the API answers /health again.

Usage in Colab (after the notebook's cells 1-3 have run once):
    !curl -sL https://raw.githubusercontent.com/digyservice-oss/Dhun/main/colab/t4_fix.py | python3
"""
import os
import subprocess
import sys
import time
import urllib.request

ACE = "/content/ACE-Step-1.5"


def patch(path, old, new):
    p = os.path.join(ACE, path)
    src = open(p, encoding="utf-8").read()
    if new in src:
        print("  already patched:", path)
        return
    if src.count(old) != 1:
        sys.exit(f"❌ Could not patch {path} (ACE-Step changed). Send this message to Claude.")
    open(p, "w", encoding="utf-8").write(src.replace(old, new))
    print("  patched:", path)


def main():
    if not os.path.isdir(ACE):
        sys.exit("❌ ACE-Step not installed yet. Run cell 1 first.")
    cap = subprocess.run(["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout.strip()
    print("GPU compute capability:", cap or "unknown")

    print("1) float16 -> float32")
    patch("acestep/core/generation/handler/init_service_orchestrator.py",
          "                else:\n                    self.dtype = torch.float16\n",
          "                else:\n                    self.dtype = torch.float32  # Dhun: fp16 overflows on pre-Ampere\n")
    patch("acestep/core/generation/handler/memory_utils.py",
          "            if cuda_supports_bfloat16(_cuda_device_index(target_device)):\n"
          "                return torch.bfloat16\n            return torch.float16\n",
          "            if cuda_supports_bfloat16(_cuda_device_index(target_device)):\n"
          "                return torch.bfloat16\n            return torch.float32  # Dhun: fp16 overflows on pre-Ampere\n")

    print("2) restarting AI engine")
    subprocess.run(["pkill", "-f", "acestep-api"])
    time.sleep(5)
    env = dict(os.environ, MPLBACKEND="Agg", ACESTEP_INIT_LLM="false",
               PATH="/root/.local/bin:" + os.environ.get("PATH", ""))
    log = open("/content/acestep.log", "w")
    proc = subprocess.Popen(["uv", "run", "acestep-api", "--host", "127.0.0.1", "--port", "8001"],
                            cwd=ACE, env=env, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)
    t0 = time.time()
    while True:
        try:
            urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=5)
            break
        except Exception:
            if proc.poll() is not None:
                print(open("/content/acestep.log").read()[-3000:])
                sys.exit("❌ AI engine stopped — send a screenshot of the log above.")
            if time.time() - t0 > 20 * 60:
                sys.exit("❌ AI engine took too long to start.")
            print(f"  waiting… {int(time.time() - t0)}s", end="\r", flush=True)
            time.sleep(5)
    print(f"\n✅ AI engine ready in float32. Dhun app link stays the same — make the song again.")


if __name__ == "__main__":
    main()
