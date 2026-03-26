# Frontend - StudyMate Chat UI

## 功能概览
- Vue 3 + Vite 单页聊天应用
- 本地会话列表（浏览器 LocalStorage）
- 与后端 `/chat/agent/session` 联调

## 运行方式
```bash
cd frontend
npm install
npm run dev
```

默认地址：`http://127.0.0.1:5173`

## 环境变量（可选）
- `VITE_API_BASE_URL`：默认 `/api`
- `VITE_API_TIMEOUT`：默认 `60000`
- `VITE_CHAT_ENDPOINT`：默认 `/chat/agent`

变量模板见根目录 `.env.example`。

## 与后端联调
`vite.config.js` 已默认代理：
- `/api/*` -> `http://127.0.0.1:8000/*`
