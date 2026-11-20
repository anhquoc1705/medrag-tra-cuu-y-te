import type { CapacitorConfig } from "@capacitor/cli";

// App Android (GĐ 10, phần thêm ngoài đề cương): đóng gói chính giao diện web (thư mục dist) bằng Capacitor.
// Trong app, giao diện chạy ở địa chỉ https://localhost → địa chỉ này phải có trong CORS_ORIGINS của backend.
// Địa chỉ backend: lấy từ VITE_API_URL lúc build, và đổi được ngay trong app (menu → "Máy chủ") – không cần build lại.
const config: CapacitorConfig = {
  appId: "vn.edu.ictu.medrag",
  appName: "Tra cứu y tế",
  webDir: "dist",
  backgroundColor: "#f6f8f7",
  server: {
    androidScheme: "https",
    // Cho phép gọi backend http (vd. http://10.0.2.2:8000 từ máy ảo, IP mạng LAN khi chạy thử).
    // Khi demo thật backend dùng https nên hai dòng này không ảnh hưởng.
    cleartext: true,
  },
  android: {
    allowMixedContent: true,
  },
};

export default config;
