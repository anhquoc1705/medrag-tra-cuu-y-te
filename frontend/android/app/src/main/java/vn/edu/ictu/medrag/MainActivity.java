package vn.edu.ictu.medrag;

import android.os.Bundle;
import androidx.activity.OnBackPressedCallback;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    // Nút Back của Android: hỏi giao diện web trước (window.medragBack – đóng ngăn nguồn / menu / hộp đăng nhập,
    // hoặc quay lại trang trước). Giao diện trả "true" = đã xử lý; ngược lại mới thoát app như mặc định.
    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                bridge.getWebView().evaluateJavascript("window.medragBack ? window.medragBack() : false", value -> {
                    if (!"true".equals(value)) {
                        setEnabled(false);
                        getOnBackPressedDispatcher().onBackPressed();
                        setEnabled(true);
                    }
                });
            }
        });
    }
}
