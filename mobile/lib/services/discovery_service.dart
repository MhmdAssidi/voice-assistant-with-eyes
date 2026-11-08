import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

/// Finds the VA Eyes server on the local network. An interface so tests can fake it.
abstract interface class ServerFinder {
  /// The server's IP address, or null if nobody answered.
  Future<String?> find();
}

/// UDP broadcast discovery (task B10): the user never has to type an IP address.
///
/// We send "VAEYES_DISCOVER" to UDP port 8765 on every network the phone is on
/// (normal Wi-Fi, and also the phone's own hotspot when the laptop is connected
/// to it), and the server's discovery responder answers. Its address is the
/// address the answer came from.
class UdpServerFinder implements ServerFinder {
  static const port = 8765;
  static const _request = 'VAEYES_DISCOVER';
  static const timeout = Duration(seconds: 3);

  @override
  Future<String?> find() async {
    RawDatagramSocket? socket;
    try {
      socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
      socket.broadcastEnabled = true;
      final found = Completer<String?>();
      socket.listen((event) {
        if (event != RawSocketEvent.read) return;
        final datagram = socket?.receive();
        if (datagram == null || found.isCompleted) return;
        if (utf8.decode(datagram.data, allowMalformed: true).contains('"va-eyes"')) {
          found.complete(datagram.address.address);
        }
      });

      final targets = await _broadcastAddresses();
      // UDP can drop a packet: try 3 times, about 1 s apart.
      for (var attempt = 0; attempt < 3 && !found.isCompleted; attempt++) {
        for (final target in targets) {
          socket.send(utf8.encode(_request), target, port);
        }
        await Future.any([found.future, Future<void>.delayed(timeout ~/ 3)]);
      }
      final host = found.isCompleted ? await found.future : null;
      debugPrint('[discovery] ${host ?? 'no server'} (asked ${targets.map((a) => a.address)})');
      return host;
    } catch (e) {
      debugPrint('[discovery] failed: $e');
      return null;
    } finally {
      socket?.close();
    }
  }

  /// 255.255.255.255 plus "x.y.z.255" for each network the phone is on. The second
  /// kind is needed for the phone's own hotspot: a plain 255.255.255.255 would
  /// leave through the mobile-data network and never reach the laptop.
  static Future<Set<InternetAddress>> _broadcastAddresses() async {
    final addresses = <InternetAddress>{InternetAddress('255.255.255.255')};
    final interfaces = await NetworkInterface.list(type: InternetAddressType.IPv4);
    for (final interface in interfaces) {
      for (final address in interface.addresses) {
        final parts = address.address.split('.');
        if (parts.length == 4) {
          addresses.add(InternetAddress('${parts[0]}.${parts[1]}.${parts[2]}.255'));
        }
      }
    }
    return addresses;
  }
}
