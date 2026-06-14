# 🚀 Deploy toàn bộ hệ thống Siupo lên Google Cloud

Hướng dẫn deploy 4 service bằng credit GCP, có CI/CD tự động (Cloud Build).

## Kiến trúc

```
                       ┌─────────────────────────────┐
  git push  ──────────▶│  Cloud Build (CI/CD)         │
                       │  build image → deploy        │
                       └─────────────┬───────────────┘
                                     ▼
   ┌──────────────┐        ┌──────────────────┐
   │ Cloud Run    │        │ Cloud Run        │
   │ siupo-be     │        │ siupo-ai-service │
   └──────┬───────┘        └────┬────────┬────┘
          │                     │        │
     ┌────▼─────┐       ┌───────▼──┐  ┌──▼──────────┐
     │ Cloud SQL│       │ Vertex AI│  │ Turso (mem) │
     │  MySQL   │       │ (Gemini) │  └─────────────┘
     └──────────┘       └──────────┘
          │                  │
     ┌────▼──────────────────▼────┐     ┌──────────────────┐
     │ VM e2-small (cùng VPC)     │     │ Firebase Hosting │
     │ Redis + Qdrant (Docker)    │     │ FE-admin / FE-cus│
     └────────────────────────────┘     └──────────────────┘
```

| Service | Chạy trên | Ghi chú |
|---|---|---|
| BE | Cloud Run | `BE/Dockerfile` + `BE/cloudbuild.yaml` |
| siupo-ai-service | Cloud Run | `Dockerfile` + `cloudbuild.yaml` |
| MySQL | Cloud SQL | nối qua socket `/cloudsql/...` |
| Redis + Qdrant | VM Compute Engine | `docker-compose.infra.yml` |
| FE-admin / FE-customer | Firebase Hosting | build tĩnh |
| Gemini | Vertex AI | đã có sẵn, credit trả phí |

---

## 0️⃣ Cấu hình ban đầu (làm 1 lần)

```bash
# Đặt project (thay PROJECT_ID của bạn)
gcloud config set project PROJECT_ID
export PROJECT_ID=$(gcloud config get-value project)
export REGION=us-central1

# Bật các API cần dùng
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  compute.googleapis.com \
  aiplatform.googleapis.com

# Tạo Artifact Registry (kho chứa Docker image)
gcloud artifacts repositories create siupo \
  --repository-format=docker --location=$REGION
```

### Cấp quyền cho service account của Cloud Build & Cloud Run

```bash
# Cloud Build SA — để deploy lên Cloud Run
PROJECT_NUM=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$PROJECT_NUM@cloudbuild.gserviceaccount.com \
  --role=roles/run.admin
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$PROJECT_NUM@cloudbuild.gserviceaccount.com \
  --role=roles/iam.serviceAccountUser

# Cloud Run runtime SA (mặc định Compute) — để AI service gọi Vertex AI bằng ADC
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$PROJECT_NUM-compute@developer.gserviceaccount.com \
  --role=roles/aiplatform.user
# ...và đọc được secret
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$PROJECT_NUM-compute@developer.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

> 💡 Nhờ ADC, AI service **không cần `service-account.json`** trên Cloud Run. File đó đã được `.dockerignore` loại khỏi image.

---

## 1️⃣ Tạo secrets (Secret Manager)

`cloudbuild.yaml` đọc secret theo tên. Tạo từng cái:

```bash
# Ví dụ 1 secret:
printf 'gia-tri-cua-ban' | gcloud secrets create QDRANT_API_KEY --data-file=-

# Cần tạo (AI service):
#   QDRANT_URL QDRANT_API_KEY SERPAPI_KEY BE_BASE_URL ADMIN_EMAIL ADMIN_PASSWORD
#   TURSO_AUTH_TOKEN TURSO_DATABASE_URL ZALO_BOT_TOKEN ZALO_WEBHOOK_SECRET
#   GMAIL_SENDER_EMAIL GMAIL_APP_PASSWORD GMAIL_ADMIN_EMAIL
#
# Cần tạo (BE):
#   SPRING_DATASOURCE_URL SPRING_DATASOURCE_USERNAME SPRING_DATASOURCE_PASSWORD
#   JWT_SECRET REDIS_HOST REDIS_PASSWORD SPRING_MAIL_USERNAME SPRING_MAIL_PASSWORD
#   APP_DEFAULT_ADMIN_EMAIL APP_DEFAULT_ADMIN_PASSWORD
```

Cập nhật giá trị mới sau này:
```bash
printf 'gia-tri-moi' | gcloud secrets versions add QDRANT_API_KEY --data-file=-
```

---

## 2️⃣ VM cho Redis + Qdrant

```bash
# Tạo VM nhỏ
gcloud compute instances create siupo-infra \
  --zone=${REGION}-a --machine-type=e2-small \
  --image-family=debian-12 --image-project=debian-cloud \
  --tags=siupo-infra

# Cho Cloud Run kết nối Redis/Qdrant qua internal IP (mở port trong VPC)
gcloud compute firewall-rules create allow-siupo-infra \
  --allow=tcp:6379,tcp:6333,tcp:6334 \
  --source-ranges=10.0.0.0/8 --target-tags=siupo-infra
```

SSH vào VM, cài Docker rồi chạy:
```bash
gcloud compute ssh siupo-infra --zone=${REGION}-a
# trên VM:
curl -fsSL https://get.docker.com | sudo sh
# copy docker-compose.infra.yml lên (hoặc git clone), rồi:
echo "REDIS_PASSWORD=mat-khau-manh" > .env
sudo docker compose -f docker-compose.infra.yml --env-file .env up -d
```

> Lấy **internal IP** của VM (`gcloud compute instances describe siupo-infra --format='value(networkInterfaces[0].networkIP)'`) rồi đặt vào secret `REDIS_HOST` và `QDRANT_URL` (`http://<internal-ip>:6333`).
> ⚠️ Cloud Run kết nối internal IP cần **Serverless VPC Connector** — tạo: `gcloud compute networks vpc-access connectors create siupo-conn --region=$REGION --range=10.8.0.0/28`, rồi thêm `--vpc-connector=siupo-conn` vào lệnh deploy. (Cách đơn giản hơn để test: dùng **Qdrant Cloud free** + **Memorystore/Upstash Redis** thay cho VM.)

---

## 3️⃣ Cloud SQL (MySQL) cho BE

```bash
gcloud sql instances create siupo-mysql \
  --database-version=MYSQL_8_0 --tier=db-f1-micro --region=$REGION
gcloud sql databases create siupo_db --instance=siupo-mysql
gcloud sql users create siupo_user --instance=siupo-mysql --password='mat-khau-db'
```

Lấy connection name (dạng `PROJECT:REGION:siupo-mysql`):
```bash
gcloud sql instances describe siupo-mysql --format='value(connectionName)'
```
→ điền vào `_CLOUDSQL_INSTANCE` trong `BE/cloudbuild.yaml`.
→ secret `SPRING_DATASOURCE_URL` đặt là:
`jdbc:mysql:///siupo_db?cloudSqlInstance=PROJECT:REGION:siupo-mysql&socketFactory=com.google.cloud.sql.mysql.SocketFactory`
*(BE cần dependency `mysql-socket-factory` trong `pom.xml`; nếu chưa có thì dùng IP public của Cloud SQL + `jdbc:mysql://IP:3306/siupo_db`.)*

---

## 4️⃣ Deploy thủ công lần đầu

```bash
# AI service
cd siupo-ai-service
gcloud builds submit --config cloudbuild.yaml

# BE
cd ../KLTN/BE
gcloud builds submit --config cloudbuild.yaml
```

Sau khi xong, lấy URL:
```bash
gcloud run services list --region=$REGION
```
→ Cập nhật secret `BE_BASE_URL` = URL của `siupo-be` (để AI service gọi BE).

---

## 5️⃣ CI/CD tự động (push là deploy)

Nối GitHub repo với Cloud Build:
```bash
# AI service
gcloud builds triggers create github \
  --name=deploy-ai-service \
  --repo-name=siupo-ai-service --repo-owner=<github-user> \
  --branch-pattern='^main$' \
  --build-config=cloudbuild.yaml

# BE (repo KLTN, build config nằm trong BE/)
gcloud builds triggers create github \
  --name=deploy-be \
  --repo-name=<repo-KLTN> --repo-owner=<github-user> \
  --branch-pattern='^main$' \
  --build-config=BE/cloudbuild.yaml \
  --included-files='BE/**'
```
Từ giờ: `git push origin main` → Cloud Build tự build + deploy. ✅

---

## 6️⃣ Frontend → Firebase Hosting

```bash
npm install -g firebase-tools
firebase login

# FE-customer
cd KLTN/FE-customer
npm install && npm run build          # ra thư mục dist/
firebase init hosting                 # chọn dist làm public dir, SPA = Yes
firebase deploy --only hosting

# FE-admin (tương tự, dùng yarn)
cd ../FE-admin
yarn install && yarn build
firebase init hosting && firebase deploy --only hosting
```
> Nhớ đặt biến môi trường API URL trong FE (file `.env`/`vite` config) trỏ về URL Cloud Run của BE & AI service trước khi build.

---

## ⚠️ Lưu ý quan trọng

1. **File upload của AI service** (`data/uploads/`) lưu trên ổ đĩa ephemeral của Cloud Run → **mất khi restart**. Nếu cần giữ lâu dài, chuyển sang **Cloud Storage (GCS)**. Demo đồ án thì tạm chấp nhận được.
2. **Conversation memory** dùng Turso (remote) → an toàn, không bị mất khi Cloud Run restart. ✅
3. **`min-instances=1`** giữ app không ngủ nhưng tốn credit liên tục. Muốn tiết kiệm tối đa → đặt `0` (chịu cold start ~vài giây).
4. **Kiểm tra hạn credit**: Console → Billing → Credits.
5. **CORS**: AI service đang mở `allow_origins=["*"]`. Production nên giới hạn theo domain Firebase.
