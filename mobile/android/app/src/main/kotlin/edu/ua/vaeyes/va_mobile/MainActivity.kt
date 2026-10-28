package edu.ua.vaeyes.va_mobile

import android.os.Bundle
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity

class MainActivity : FlutterActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // The camera streams the whole time the app is open, and Android stops
        // the camera when the screen turns off. So the screen stays on while
        // this app is in front (the flag is dropped automatically when it is not).
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }
}
