import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// Answer to a question, mirrors AskResponse in backend/app/contracts.py.
class AskResponse {
  const AskResponse({
    required this.id,
    required this.question,
    required this.language,
    required this.answer,
    required this.confident,
    required this.timingsMs,
  });

  factory AskResponse.fromJson(Map<String, dynamic> json) => AskResponse(
        id: json['id'] as int,
        question: json['question'] as String,
        language: json['language'] as String,
        answer: json['answer'] as String,
        confident: json['confident'] as bool,
        timingsMs: (json['timings_ms'] as Map<String, dynamic>? ?? {})
            .map((key, value) => MapEntry(key, value as int)),
      );

  final int id;
  final String question;

  /// Language of the question: "en", "fr" or "ar" (used to speak it, B9).
  final String language;

  /// 1-2 short sentences, ready to speak.
  final String answer;
  final bool confident;
  final Map<String, int> timingsMs;

  // "evidence" (frames used for the answer) is not needed on the phone;
  // the dashboard History page shows it (B11).
}

/// The server answered, but with an error (HTTP status other than 200).
class ApiException implements Exception {
  ApiException(this.statusCode, this.body);

  final int statusCode;
  final String body;

  @override
  String toString() => 'ApiException($statusCode): $body';
}

/// Talks to the backend API on the laptop (port 8000).
class ApiClient {
  ApiClient({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  static const apiPort = 8000;

  /// Speech-to-text + search + vision model can take a while on a CPU laptop.
  static const askTimeout = Duration(seconds: 30);

  static Uri baseUri(String host) => Uri(scheme: 'http', host: host, port: apiPort);

  /// True if GET /api/health answers {"status":"ok"} within 3 seconds.
  Future<bool> isServerReachable(String host) async {
    try {
      final request = http.Request('GET', baseUri(host).replace(path: '/api/health'))
        ..persistentConnection = false; // see the note below
      final response = await _client.send(request).timeout(const Duration(seconds: 3));
      await response.stream.drain<void>();
      return response.statusCode == 200;
    } catch (e) {
      // Timeout, no route to host, connection refused...: all mean "not reachable".
      debugPrint('[api] health check failed: $e');
      return false;
    }
  }

  // Why every request uses a fresh connection (persistentConnection = false):
  // uvicorn closes idle connections after 5 s and we poll every 5 s, so a
  // reused connection was sometimes closed by the server at the very moment we
  // sent on it ("connection aborted") -> the app flashed "server unreachable".

  /// Uploads the recorded question (multipart: "audio" + "lang_hint") to
  /// POST /api/ask. Throws TimeoutException after [askTimeout].
  Future<AskResponse> ask(String host, String audioPath, {String? langHint}) async {
    final request = http.MultipartRequest('POST', baseUri(host).replace(path: '/api/ask'))
      ..persistentConnection = false // see the note above
      ..files.add(await http.MultipartFile.fromPath('audio', audioPath))
      ..fields.addAll({'lang_hint': ?langHint});

    final response = await _client
        .send(request)
        .then(http.Response.fromStream)
        .timeout(askTimeout);
    if (response.statusCode != 200) {
      throw ApiException(response.statusCode, response.body);
    }
    // Decode as UTF-8 explicitly so French and Arabic answers stay correct.
    final json = jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    return AskResponse.fromJson(json);
  }
}
