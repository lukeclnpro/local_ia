# Local IA

Installation et lancement de **Local IA** sur CachyOS et Windows.

## 🐧 CachyOS
```bash
git clone https://github.com/lukeclnpro/local_ia.git
cd local_ia
sudo pacman -Syu --needed --noconfirm python python-pip python-virtualenv curl git base-devel
python ollama_test.py
sudo systemctl enable --now ollama
ollama pull qwen2.5:1.5b
python3 -m venv .venv
. .venv/bin/activate.fish
python -m pip install --upgrade pip
chmod +x ia_agent.py
python ia_agent.py

```

---

## 🪟 Windows
```powershell
cd $HOME/Documents
git clone https://github.com/lukeclnpro/local_ia.git
cd local_ia
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
python ollama_test.py
winget install Python.Python.3 Git.Git Ollama.Ollama
ollama pull qwen2.5:1.5b
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python ia_agent.py

```
