import 'package:http/http.dart' as http;

/// Talks to the backend API on the laptop (port 8000).
///
/// B2: health check only. B5 adds the question upload (POST /api/ask).
class ApiClient {
  ApiClient({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  static const apiPort = 8000;

  static Uri baseUri(String host) => Uri(scheme: 'http', host: host, port: apiPort);

  /// True if GET /api/health answers {"status":"ok"} within 3 seconds.
  Future<bool> isServerReachable(String host) async {
    try {
      final response = await _client
          .get(baseUri(host).replace(path: '/api/health'))
          .timeout(const Duration(seconds: 3));
      return response.statusCode == 200;
    } catch (_) {
      // Timeout, no route to host, connection refused...: all mean "not reachable".
      return false;
    }
  }
}
