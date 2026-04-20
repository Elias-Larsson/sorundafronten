# sorundafronten

borde hetat JÄRREBOMB

## Starta backend (FastAPI)

### 1. Gå till backend-mappen

```powershell
cd backend
```

### 2. Skapa och aktivera virtuellt miljö (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Installera beroenden

```powershell
pip install fastapi uvicorn
```

### 4. Starta servern

```powershell
uvicorn main:app --reload
```

Servern startar normalt på:

`http://127.0.0.1:8000`

### 5. Testa att backend fungerar

- API root: `http://127.0.0.1:8000/`
- Swagger UI: `http://127.0.0.1:8000/docs`
