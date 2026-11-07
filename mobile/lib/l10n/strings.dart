import 'package:flutter/widgets.dart';

/// Every text the app shows or announces, in English, French and Arabic.
///
/// The language is the user's preferred language from the settings screen.
/// (Spoken answers follow the language of the question, see B9.)
class AppStrings {
  const AppStrings._({
    required this.appTitle,
    required this.settings,
    required this.askButton,
    required this.stopButton,
    required this.askHint,
    required this.statusConnecting,
    required this.statusNoServer,
    required this.statusOffline,
    required this.statusReady,
    required this.statusListening,
    required this.statusThinking,
    required this.statusSpeaking,
    required this.stopSpeakingButton,
    required this.voicesTitle,
    required this.voiceMissing,
    required this.statusError,
    required this.lastAnswer,
    required this.noAnswerYet,
    required this.micDenied,
    required this.tooShort,
    required this.serverTooSlow,
    required this.serverAddress,
    required this.serverAddressHint,
    required this.serverAddressInvalid,
    required this.language,
    required this.save,
    required this.saved,
    required this.cameraConnected,
    required this.cameraDisconnected,
    required this.cameraConnecting,
    required this.cameraOff,
    required this.warningClosedDoor,
    required this.warningStairs,
  });

  final String appTitle;
  final String settings;
  final String askButton;
  final String stopButton;
  final String askHint;
  final String statusConnecting;
  final String statusNoServer;
  final String statusOffline;
  final String statusReady;
  final String statusListening;
  final String statusThinking;
  final String statusSpeaking;
  final String stopSpeakingButton;
  final String voicesTitle;
  final String voiceMissing;
  final String statusError;
  final String lastAnswer;
  final String noAnswerYet;
  final String micDenied;
  final String tooShort;
  final String serverTooSlow;
  final String serverAddress;
  final String serverAddressHint;
  final String serverAddressInvalid;
  final String language;
  final String save;
  final String saved;
  final String cameraConnected;
  final String cameraDisconnected;
  final String cameraConnecting;
  final String cameraOff;

  /// Spoken warnings (B12). A door warning is only a hint (Student A's detector is
  /// less sure about doors than stairs), hence "there may be".
  final String warningClosedDoor;
  final String warningStairs;

  /// Supported languages: code -> name written in that language.
  static const languages = {'en': 'English', 'fr': 'Français', 'ar': 'العربية'};

  static AppStrings of(String languageCode) => switch (languageCode) {
        'fr' => _fr,
        'ar' => _ar,
        _ => _en,
      };

  static TextDirection directionOf(String languageCode) =>
      languageCode == 'ar' ? TextDirection.rtl : TextDirection.ltr;

  static const _en = AppStrings._(
    appTitle: 'VA Eyes',
    settings: 'Settings',
    askButton: 'Ask a question',
    stopButton: 'Stop and send',
    askHint: 'Tap to start speaking, tap again to send.',
    statusConnecting: 'Connecting to the server…',
    statusNoServer: 'Set the server address in Settings.',
    statusOffline: 'Server not reachable. Check the Wi-Fi and the server address.',
    statusReady: 'Ready. Tap the big button to ask.',
    statusListening: 'Listening. Tap again to stop.',
    statusThinking: 'Thinking…',
    statusSpeaking: 'Reading the answer. Tap to stop.',
    stopSpeakingButton: 'Stop reading',
    voicesTitle: 'Voices on this phone',
    voiceMissing:
        'Missing voice: Android Settings → General management → Text-to-speech → install the language.',
    statusError: 'Something went wrong. Please try again.',
    lastAnswer: 'Last answer',
    noAnswerYet: 'No answer yet.',
    micDenied: 'Microphone permission is needed to ask questions. Allow it in the phone settings.',
    tooShort: 'I didn’t hear anything. Tap and speak again.',
    serverTooSlow: 'The server took too long to answer. Please try again.',
    serverAddress: 'Server IP address',
    serverAddressHint: 'For example 192.168.0.105',
    serverAddressInvalid: 'Enter an address like 192.168.0.105',
    language: 'Language',
    save: 'Save',
    saved: 'Settings saved.',
    cameraConnected: 'Camera connected.',
    cameraDisconnected: 'Camera disconnected.',
    cameraConnecting: 'Connecting the camera…',
    cameraOff: 'Camera off.',
    warningClosedDoor: 'Careful: there may be a closed door ahead.',
    warningStairs: 'Careful: stairs ahead.',
  );

  static const _fr = AppStrings._(
    appTitle: 'VA Eyes',
    settings: 'Réglages',
    askButton: 'Poser une question',
    stopButton: 'Arrêter et envoyer',
    askHint: 'Touchez pour parler, touchez à nouveau pour envoyer.',
    statusConnecting: 'Connexion au serveur…',
    statusNoServer: 'Indiquez l’adresse du serveur dans les réglages.',
    statusOffline: 'Serveur injoignable. Vérifiez le Wi-Fi et l’adresse du serveur.',
    statusReady: 'Prêt. Touchez le grand bouton pour poser une question.',
    statusListening: 'J’écoute. Touchez à nouveau pour arrêter.',
    statusThinking: 'Je réfléchis…',
    statusSpeaking: 'Lecture de la réponse. Touchez pour arrêter.',
    stopSpeakingButton: 'Arrêter la lecture',
    voicesTitle: 'Voix sur ce téléphone',
    voiceMissing:
        'Voix manquante : Paramètres Android → Gestion globale → Synthèse vocale → installer la langue.',
    statusError: 'Une erreur s’est produite. Veuillez réessayer.',
    lastAnswer: 'Dernière réponse',
    noAnswerYet: 'Pas encore de réponse.',
    micDenied:
        'L’accès au micro est nécessaire pour poser des questions. Autorisez-le dans les réglages du téléphone.',
    tooShort: 'Je n’ai rien entendu. Touchez et parlez à nouveau.',
    serverTooSlow: 'Le serveur a mis trop de temps à répondre. Veuillez réessayer.',
    serverAddress: 'Adresse IP du serveur',
    serverAddressHint: 'Par exemple 192.168.0.105',
    serverAddressInvalid: 'Entrez une adresse comme 192.168.0.105',
    language: 'Langue',
    save: 'Enregistrer',
    saved: 'Réglages enregistrés.',
    cameraConnected: 'Caméra connectée.',
    cameraDisconnected: 'Caméra déconnectée.',
    cameraConnecting: 'Connexion de la caméra…',
    cameraOff: 'Caméra éteinte.',
    warningClosedDoor: 'Attention : il y a peut-être une porte fermée devant vous.',
    warningStairs: 'Attention : escalier devant vous.',
  );

  static const _ar = AppStrings._(
    appTitle: 'VA Eyes',
    settings: 'الإعدادات',
    askButton: 'اطرح سؤالاً',
    stopButton: 'أوقف وأرسل',
    askHint: 'انقر لبدء الكلام، ثم انقر مرة أخرى للإرسال.',
    statusConnecting: 'جارٍ الاتصال بالخادم…',
    statusNoServer: 'أدخل عنوان الخادم في الإعدادات.',
    statusOffline: 'تعذّر الوصول إلى الخادم. تحقّق من شبكة الواي فاي وعنوان الخادم.',
    statusReady: 'جاهز. انقر على الزر الكبير لطرح سؤال.',
    statusListening: 'أستمع. انقر مرة أخرى للإيقاف.',
    statusThinking: 'أفكّر…',
    statusSpeaking: 'أقرأ الإجابة. انقر للإيقاف.',
    stopSpeakingButton: 'أوقف القراءة',
    voicesTitle: 'الأصوات على هذا الهاتف',
    voiceMissing: 'صوت ناقص: إعدادات أندرويد ← الإدارة العامة ← تحويل النص إلى كلام ← ثبّت اللغة.',
    statusError: 'حدث خطأ. يرجى المحاولة مرة أخرى.',
    lastAnswer: 'آخر إجابة',
    noAnswerYet: 'لا توجد إجابة بعد.',
    micDenied: 'يلزم إذن الميكروفون لطرح الأسئلة. اسمح به في إعدادات الهاتف.',
    tooShort: 'لم أسمع شيئًا. انقر وتحدّث مرة أخرى.',
    serverTooSlow: 'استغرق الخادم وقتًا طويلاً للرد. يرجى المحاولة مرة أخرى.',
    serverAddress: 'عنوان IP للخادم',
    serverAddressHint: 'مثلاً 192.168.0.105',
    serverAddressInvalid: 'أدخل عنوانًا مثل 192.168.0.105',
    language: 'اللغة',
    save: 'حفظ',
    saved: 'تم حفظ الإعدادات.',
    cameraConnected: 'الكاميرا متصلة.',
    cameraDisconnected: 'الكاميرا غير متصلة.',
    cameraConnecting: 'جارٍ توصيل الكاميرا…',
    cameraOff: 'الكاميرا متوقفة.',
    warningClosedDoor: 'انتبه: قد يكون هناك باب مغلق أمامك.',
    warningStairs: 'انتبه: يوجد درج أمامك.',
  );
}
