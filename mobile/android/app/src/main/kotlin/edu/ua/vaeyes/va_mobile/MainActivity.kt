package edu.ua.vaeyes.va_mobile

import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Bundle
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private var tones: ToneGenerator? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // The camera streams the whole time the app is open, and Android stops
        // the camera when the screen turns off. So the screen stays on while
        // this app is in front (the flag is dropped automatically when it is not).
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        // Short beeps when recording starts/stops (B5). Android's built-in tone
        // generator, so no audio files or extra packages are needed.
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "edu.ua.vaeyes/cues")
            .setMethodCallHandler { call, result ->
                if (call.method == "beep") {
                    val tone = if (call.argument<String>("kind") == "stop") {
                        ToneGenerator.TONE_PROP_ACK // two short beeps
                    } else {
                        ToneGenerator.TONE_PROP_BEEP // one short beep
                    }
                    try {
                        val generator = tones ?: ToneGenerator(AudioManager.STREAM_MUSIC, 80)
                        tones = generator
                        generator.startTone(tone, 150)
                    } catch (e: RuntimeException) {
                        // No tone on this device: the vibration still gives feedback.
                    }
                    result.success(null)
                } else {
                    result.notImplemented()
                }
            }
    }

    override fun onDestroy() {
        tones?.release()
        tones = null
        super.onDestroy()
    }
}
