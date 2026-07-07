# Huong Dan Chay Lai Du An Sau Khi Restart May

Tai lieu nay dung cho Windows PowerShell, workspace hien tai la `D:\attacker`.

## 1. Kiem Tra Moi Truong

Mo PowerShell moi va chay:

```powershell
cd D:\attacker
python --version
node --version
npm --version
```

Neu `python`, `node` hoac `npm` khong nhan lenh, can cai dat hoac them vao `PATH` truoc khi chay du an.

## 2. Kiem Tra Port Dang Duoc Dung

Du an mac dinh dung:

- Backend FastAPI: `127.0.0.1:8000`
- Frontend Vite: `127.0.0.1:5173`
- Frontend preview build: `127.0.0.1:4173`

Kiem tra port:

```powershell
netstat -ano | Select-String ':8000|:5173|:4173'
```

Neu khong co dong nao hien ra, cac port dang trong.

Neu co dong `LISTENING`, lay PID o cot cuoi va xem tien trinh:

```powershell
Get-Process -Id <PID>
```

Dung tien trinh neu do la server cu cua du an:

```powershell
Stop-Process -Id <PID>
```

Vi du:

```powershell
Stop-Process -Id 23504
```

Neu khong chac PID do la gi, khong nen dung voi. Kiem tra `ProcessName` truoc.

## 3. Cai Dat Dependency Lan Dau Hoac Sau Khi Node Modules Bi Mat

Chay backend dependencies:

```powershell
cd D:\attacker
python -m pip install -r backend/requirements.txt
```

Chay frontend dependencies:

```powershell
cd D:\attacker\frontend
npm install
```

Sau khi da cai mot lan, thuong khong can chay lai `pip install` va `npm install` moi lan restart.

## 4. Khoi Tao Lai Du Lieu Demo

Neu muon reset demo ve trang thai sach:

```powershell
cd D:\attacker
python scripts/generate_synthetic_data.py
python scripts/seed_database.py
```

Lenh nay tao lai CSV synthetic va seed vao SQLite:

```text
backend/app/data/vietsupply.db
```

Neu chi muon chay lai app ma giu audit/request vua tao, co the bo qua buoc generate/seed. Tuy nhien sau khi restart may, de demo on dinh nhat nen seed lai.

Kiem tra du lieu:

```powershell
python scripts/validate_data.py
```

Ket qua dung se co dang:

```text
Data validation passed: 62 businesses, 120 edges, 12 months financials, BIZ-005 shock scenario ready.
```

## 4.1. Tuy Chon: Chay PostgreSQL RLS Smoke Cho Pilot

Buoc nay chi can khi kiem tra trust gate cho pilot/production. Demo SQLite khong can buoc nay.

Neu da co PostgreSQL/PostGIS test database:

```powershell
cd D:\attacker
$env:POSTGRES_TEST_DATABASE_URL="postgresql://user:password@localhost:5432/vietsupply_smoke"
python scripts/postgres_rls_smoke.py
```

Neu may co Docker Desktop, co the tao container PostGIS tam thoi va tu dong chay smoke:

```powershell
cd D:\attacker
powershell -ExecutionPolicy Bypass -File scripts/run_postgres_rls_smoke_docker.ps1
```

Script Docker se xoa container tam sau khi chay xong. Muon giu container de debug:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_postgres_rls_smoke_docker.ps1 -KeepContainer
```

Kiem tra trust readiness gate truoc khi noi du an san sang pilot:

```powershell
cd D:\attacker
python scripts/run_trust_readiness_gate.py
```

Neu chi dang chay local demo va chua co PostgreSQL/OIDC/S3-MinIO live, dung che do nay:

```powershell
python scripts/run_trust_readiness_gate.py --allow-missing-live
```

Neu co Docker Desktop va muon chay live proof cho evidence storage/scanner bang MinIO + ClamAV disposable:

```powershell
cd D:\attacker
powershell -ExecutionPolicy Bypass -File scripts/run_evidence_live_smoke_docker.ps1
```

Neu muon chay kem readiness gate voi hai evidence live flags, nhung van cho phep thieu OIDC/PostgreSQL live proof:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_evidence_live_smoke_docker.ps1 -RunReadinessGate
```

Lenh nay co the pass local gate nhung van tra `pilot_ready=false` neu thieu bang chung live.

Kiem tra rieng OIDC verifier bang local synthetic JWKS. Day chi chung minh co che verifier, khong phai pilot proof:

```powershell
python scripts/run_oidc_jwks_smoke.py --synthetic --json
```

Khi da cau hinh issuer/JWKS that, dung mot token test co chu ky tu issuer do de chay live proof. Buoc nay chi chung minh lat cat OIDC; full readiness gate van can PostgreSQL RLS, S3/MinIO PUT/GET/DELETE cleanup va ClamAV live proof:

```powershell
$env:APP_MODE="pilot"
$env:ALLOW_DEMO_HEADERS="false"
$env:AUTH_PROVIDER="oidc"
$env:AUTH_JWKS_URL="https://issuer.example/.well-known/jwks.json"
$env:AUTH_JWT_ISSUER="https://issuer.example/"
$env:AUTH_JWT_AUDIENCE="vietsupply-api"
$env:OIDC_SMOKE_TOKEN="<signed test token from issuer>"
python scripts/run_oidc_jwks_smoke.py --json
$env:OIDC_SIGNED_TOKEN_LIVE_SMOKE="1"
python scripts/run_trust_readiness_gate.py
```

Kiem tra local operational smoke gate cho SQLite demo adapter:

```powershell
python scripts/run_local_operational_smoke.py
```

Lenh nay kiem tra seed count, backup/restore SQLite, masked graph redaction, security negative checks, audit tamper detection va latency baseline local. Day khong thay the live PostgreSQL/RLS/OIDC/object-storage/malware-scanner proof.

## 5. Chay Backend API

Mo Terminal 1:

```powershell
cd D:\attacker
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Neu thanh cong se thay:

```text
Uvicorn running on http://127.0.0.1:8000
```

Khong dong terminal nay trong luc dang demo.

Kiem tra backend bang trinh duyet:

- `http://127.0.0.1:8000/api/v1/health`
- `http://127.0.0.1:8000/docs`

Hoac kiem tra bang PowerShell:

```powershell
@'
import json
from urllib.request import urlopen

with urlopen("http://127.0.0.1:8000/api/v1/health", timeout=10) as response:
    print(json.dumps(json.load(response), indent=2))
'@ | python -
```

## 6. Chay Frontend Web

Mo Terminal 2:

```powershell
cd D:\attacker\frontend
npm run dev
```

Script `npm run dev` da cau hinh san:

```text
vite --host 127.0.0.1 --port 5173
```

Neu thanh cong se thay:

```text
Local: http://127.0.0.1:5173/
```

Mo web:

```text
http://127.0.0.1:5173
```

Khong dong terminal nay trong luc dang demo.

## 7. Thu Tu Chay Dung Sau Khi Restart

Dung thu tu ngan gon nay:

Terminal 1:

```powershell
cd D:\attacker
python scripts/generate_synthetic_data.py
python scripts/seed_database.py
python scripts/validate_data.py
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
cd D:\attacker\frontend
npm run dev
```

Sau do mo:

```text
http://127.0.0.1:5173
```

## 8. Chay Voi Port Khac Neu Port Bi Ban

### Backend port khac

Vi du doi backend sang port `8001`:

```powershell
cd D:\attacker
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001
```

Khi doi backend port, frontend can biet API moi. Mo Terminal frontend va set env truoc khi chay:

```powershell
cd D:\attacker\frontend
$env:VITE_API_BASE_URL="http://127.0.0.1:8001"
npm run dev
```

### Frontend port khac

Vi du doi frontend sang port `5174`:

```powershell
cd D:\attacker\frontend
npm run dev -- --host 127.0.0.1 --port 5174
```

Mo:

```text
http://127.0.0.1:5174
```

Luu y: backend CORS hien cho phep `http://127.0.0.1:5173` va `http://localhost:5173`. Neu doi frontend sang port khac va API bi chan CORS, nen dung lai port `5173` hoac cap nhat CORS trong `backend/app/main.py`.

## 9. Chay Server An Trong Nen

Neu muon chay backend/frontend an trong nen sau restart:

```powershell
cd D:\attacker
New-Item -ItemType Directory -Force logs | Out-Null

Start-Process -FilePath python `
  -ArgumentList @('-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000') `
  -WorkingDirectory 'D:\attacker' `
  -WindowStyle Hidden `
  -RedirectStandardOutput 'D:\attacker\logs\backend.log' `
  -RedirectStandardError 'D:\attacker\logs\backend.err.log'

Start-Process -FilePath npm.cmd `
  -ArgumentList @('run','dev') `
  -WorkingDirectory 'D:\attacker\frontend' `
  -WindowStyle Hidden `
  -RedirectStandardOutput 'D:\attacker\logs\frontend.log' `
  -RedirectStandardError 'D:\attacker\logs\frontend.err.log'
```

Kiem tra log:

```powershell
Get-Content -Tail 40 D:\attacker\logs\backend.err.log
Get-Content -Tail 40 D:\attacker\logs\frontend.log
```

Kiem tra port:

```powershell
netstat -ano | Select-String ':8000|:5173'
```

## 10. Dung Server

Neu dang chay trong terminal foreground:

- Bam `Ctrl + C` o Terminal backend.
- Bam `Ctrl + C` o Terminal frontend.

Neu dang chay nen bang `Start-Process`, tim PID:

```powershell
netstat -ano | Select-String ':8000|:5173'
```

Dung PID backend/frontend:

```powershell
Stop-Process -Id <PID>
```

## 11. Kiem Tra Toan Bo Du An

Chay backend unit test:

```powershell
cd D:\attacker
python -m unittest discover -s backend\tests
```

Build frontend:

```powershell
cd D:\attacker\frontend
npm run build
```

API smoke test:

```powershell
@'
import json
from urllib.request import urlopen

base = "http://127.0.0.1:8000"
paths = [
    "/api/v1/health",
    "/api/v1/demo/scenario",
    "/api/v1/businesses/BIZ-005/evidence",
    "/api/v1/businesses/BIZ-005/risk-signal",
    "/api/v1/businesses/BIZ-005/finance",
    "/api/v1/audit",
]

for path in paths:
    with urlopen(base + path, timeout=10) as response:
        payload = json.load(response)
    print(path, response.status, sorted(payload.keys()))
'@ | python -
```

## 12. Loi Thuong Gap

### Loi `Address already in use`

Port dang bi tien trinh khac chiem. Kiem tra:

```powershell
netstat -ano | Select-String ':8000|:5173'
```

Dung PID cu hoac doi port theo muc 8.

### Frontend mo duoc nhung hien fallback/mock

Backend chua chay hoac `VITE_API_BASE_URL` sai. Kiem tra:

```powershell
http://127.0.0.1:8000/api/v1/health
```

Neu API khong mo duoc, chay lai backend.

### Map khong hien tile nen

Map dung tile CARTO qua internet. Neu mat internet, node/edge SVG van co the render nhung nen ban do co the khong tai duoc.

### `python` khong nhan lenh

Cai Python hoac them Python vao PATH. Co the thu:

```powershell
py --version
py -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

### `npm` khong nhan lenh

Cai Node.js LTS va mo lai PowerShell.

## 13. Checklist Demo Nhanh

Sau khi mo `http://127.0.0.1:5173`, kiem tra:

- Left nav co cac man: Overview, Supply Map, Companies & Evidence, Risk Analysis, Matching, Finance, Invoice Verification, Audit Trail.
- Overview hien map mien Nam Viet Nam va Binh Duong focus.
- Nut `Run` chay duoc shock simulation.
- Risk Analysis hien rule trace va evidence chain.
- Matching hien top 3 supplier alternatives va nut `Request introduction`.
- Audit Trail ghi event sau khi request introduction.
- Finance hien cash flow va health score.
- Invoice Verification hien hash comparison va guarantee band.
