import gc
import os
import re
import json
import time
import socket
import machine
import network
import uhashlib as hashlib
import uasyncio as asyncio
import ubinascii as binascii

from websocket import websocket as base_websocket


led = machine.Pin('LED', machine.Pin.OUT)


def url_decode(encoded: str):
    i = 0
    decoded: str = ''

    while i < len(encoded):
        if encoded[i] == '%':
            decoded += chr(int(encoded[i + 1:i + 3], 16))
            i += 3
        else:
            decoded += encoded[i]
            i += 1

    return decoded
    

class Tz:

    def __init__(self, data: dict = {}):
        for k, v in data.items():
            if isinstance(v, dict):
                v = Tz(v)
            elif isinstance(v, list):
                for i, vv in enumerate(v):
                    v[i] = Tz(vv) if isinstance(vv, dict) else vv
                        
            setattr(self, k, v)

    def __getitem__(self, k: str) -> any:
        return getattr(self, k)
    
    def __str__(self) -> str:
        return str(self.__dict__)
    
    def __len__(self) -> int:
        return len(self.__dict__)
    
    def items(self) -> dict[str, any]:
        return self.__dict__.items()
    

class Tf:

    @staticmethod
    def set(name: str, content: str) -> str:
        content = str(content).replace('"', '\\"')

        return exec(f'{name} = "{content}"') or ''

    @staticmethod
    def echo(content: str, context: dict = {}, times: iter = [0]) -> str:
        global k, v, i, item

        if (content := str(content)) and (content.endswith('.html') or content.endswith('.tpl')):
            with open(content, 'r') as f:
                content = f.read()
        elif content.endswith('.py'):
            with open(content, 'r') as f:
                return exec(f.read()) or ''
        
        for k, v in context.items():
            if not isinstance(v, dict):
                exec(f'{k} = v')
            else:
                exec(f'{k} = Tz(v)') 

            del k, v

        if isinstance(times, (Tz, dict)):
            times = times.items()
        elif isinstance(times, list):
            times = enumerate(times)
        else:
            raise TypeError('times must be iterable')
        
        echo = ''

        for i, item in times:
            try:
                if not isinstance(item, dict):
                    item = item
                else:
                    item = Tz(item)

                # , r'\{\s*(.*?)\s*\}'
                for pattern in [r'\<\?\=\s*(.*?)\s*\?\>']:
                    content = re.sub(pattern, lambda match: str(eval(match.group(1) or '')), content)

                echo += content
            except Exception as e:
                raise e

        return echo

    @staticmethod
    def match(expression: str, then: str|dict):
        return Tf.Statement().match(expression, then)

    class Statement:

        def __init__(self):
            self.content: str = False

        def match(self, expression: str, then: str|dict):
            if not isinstance(then, (str, dict)):
                raise TypeError('then must be str or dict')

            global k, v

            if self.content == False and eval(str(expression)):
                if isinstance(then, dict):
                    self.content = ''

                    for k, v in then.items():
                        if not isinstance(v, dict):
                            exec(f'{k} = v')
                        else:
                            exec(f'{k} = Tz(v)') 

                        del k, v
                else:
                    self.content = str(then)

            return self
        
        def nomatch(self, then: str|dict = '') -> str:
            if not isinstance(then, (str, dict)):
                raise TypeError('then must be str or dict')

            global k, v

            if self.content == False:
                if isinstance(then, dict):
                    self.content = ''

                    for k, v in then.items():
                        if not isinstance(v, dict):
                            exec(f'{k} = v')
                        else:
                            exec(f'{k} = Tz(v)') 

                        del k, v
                else:
                    self.content = str(then)

            return Tf.echo(self.content)


class HTTP:

    STATUS_OK: int = 200
    STATUS_NO_CONTENT: int = 204
    STATUS_MOVED_PERMANENTLY: int = 301
    STATUS_MOVED_TEMPORARY: int = 302
    STATUS_TEMPORARY_REDIRECT: int = 307
    STATUS_BAD_REQUEST: int = 400
    STATUS_UNAUTHORIZED: int = 401
    STATUS_FORBIDDEN: int = 403
    STATUS_NOT_FOUND: int = 404
    STATUS_LENGTH_REQUIRED: int = 411
    STATUS_UNSUPPORTED_MEDIA_TYPE: int = 415
    STATUS_UNPROCESSABLE_ENTITY: int = 422
    STATUS_INTERNAL_SERVER_ERROR: int = 500

    HEADER_CONTENT_TYPE: dict = {
        'html': 'text/html',
        'css': 'text/css',
        'js': 'application/javascript',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp',
        'ico': 'image/x-icon',
        'svg': 'image/svg+xml',
        'json': 'application/json',
        'xml': 'application/xml',
        'pdf': 'application/pdf',
        'zip': 'application/zip',
        'txt': 'text/plain',
        'csv': 'text/csv',
        'mp3': 'audio/mpeg',
        'mp4': 'video/mp4',
        'wav': 'audio/wav',
        'ogg': 'audio/ogg',
        'webm': 'video/webm',
    }

    def __init__(self):
        self.request = self.Request()
        self.response = self.Response()

    def add_background_task(self, callback: callable, kwargs: dict = {}):
        loop = asyncio.get_event_loop()
        loop.create_task(callback(**kwargs))

    class Request:

        def __init__(self):
            self.url: str = ''
            self.method: str = 'GET'
            self.params: dict = {}
            self.headers: dict = {}
            self.post_data: dict = {}

        def redirect_to(self, url: str):
            raise NotImplementedError()
        
    class Response:

        def __init__(self):
            self.content: str = ''
            self.content_type: str = 'text/html'
            self.content_headers: dict = {}

        def template(self, content: str, context: dict = {}) -> tuple[bool, str]:
            try:
                return (True, Tf.echo(content, context))
            except Exception as e:
                return (False, f'Response.template("{content}"): {e}')
    
        def attachment(self, filename: str) -> int:
            try:
                if os.stat(filename)[0] & 0x4000 == 0:
                    with open(filename, 'rb') as f:
                        self.content = f.read()
                        self.content_type = HTTP.HEADER_CONTENT_TYPE.get(filename.lower().split('.')[-1], 'application/octet-stream')
                        self.content_headers['Content-disposition'] = f'attachment; filename="{filename.split("/")[-1]}"'

                    return HTTP.STATUS_OK
                else:
                    raise FileNotFoundError()
            except Exception as e:
                print(f'RouterHTTP.Response.attachment("{filename}"): {e}')
            
            return HTTP.STATUS_NOT_FOUND


class WebsocketClosed(Exception):
    pass


class Websocket:

    max_connections: int = -1
    connections_alive: list['Websocket'] = []

    @property
    def token(self) -> str:
        return self.headers.get('Sec-WebSocket-Key', '')

    @property
    def token_digest(self) -> str:
        d = hashlib.sha1(self.token)
        d.update('258EAFA5-E914-47DA-95CA-C5AB0DC85B11')
        
        return (binascii.b2a_base64(d.digest())[:-1]).decode()
    
    @property
    def socket_state(self) -> int:
        if self.is_closed:
            return 4

        return int((str(self.__socket).split(' ')[1]).split('=')[1])

    @property
    def is_closed(self) -> bool:
        return self.__socket is None
    
    @staticmethod
    def broadcast(message: str):
        for websocket in Websocket.connections_alive:
            websocket.send(message)

    @staticmethod
    def is_enough() -> bool:
        return Websocket.max_connections > 0 and len(Websocket.connections_alive) >= Websocket.max_connections
    
    @staticmethod
    def set_max_connections(limit_count: int):
        Websocket.max_connections = limit_count
    
    @staticmethod
    async def close_dead_sockets():
        while True:
            for websocket in Websocket.connections_alive:
                if websocket.is_closed:
                    Websocket.connections_alive.remove(websocket)
            
            await asyncio.sleep(1)

    def __init__(self, client: socket.socket, IP: tuple[str, int]):
        self.IP = IP
        self.headers: dict[str, str] = {}

        self.__socket: socket.socket = client
        self.__websocket: base_websocket = base_websocket(self.__socket, True)
        self.__socket.setblocking(False)
        self.__socket.setsockopt(socket.SOL_SOCKET, 20, self.__heartbeat)

    def __heartbeat(self, _):
        if self.socket_state == 4:
            self.close()

    def open(self):
        Websocket.connections_alive.append(self)
        print('Connection opened:', str(self.IP))

    def recv(self, decode_to: str = 'utf-8'):
        if self.socket_state == 4:
            return self.close()
        
        if self.is_closed:
            raise WebsocketClosed

        try:
            if (message := self.__websocket.read()):
                if decode_to:
                    return message.decode(decode_to)

                return message
        except OSError:
            self.close()

    def send(self, message: str):
        if self.is_closed:
            raise WebsocketClosed

        try:
            self.__websocket.write(message)
        except OSError:
            self.close()

    def close(self):
        if self.__socket is not None:
            print('Connection closed:', str(self.IP))
            self.__socket.setsockopt(socket.SOL_SOCKET, 20, None)
            self.__socket.close()
            self.__socket = self.__websocket = None

            for websocket in Websocket.connections_alive:
                if self is websocket:
                    Websocket.connections_alive.remove(websocket)

class RouterHTTP():

    @property
    def is_connected(self) -> bool:
        return self.wlan.isconnected()

    def __init__(self):
        self.wlan: network.WLAN = network.WLAN(network.STA_IF)
        self.wlan.active(False)
        self.hashmap: dict[str, dict] = {'http': {}, 'status': {}, 'static': {}, 'websocket': {}}

    def connect_wlan(self, ssid: str, password: str) -> bool:
        self.wlan.active(True)
        self.wlan.connect(ssid, password)

        for c in range(0, 2):
            time.sleep(1)

            if self.wlan.status() < 0 or self.wlan.status() >= 3:
                break

            time.sleep(4)

        if self.wlan.isconnected():
            self.ifconfig = self.wlan.ifconfig()
            print(f'$ Connection succeeded to WiFi = {ssid} with IP = {self.ifconfig[0]}')

        return self.wlan.isconnected()
    
    def mount(self, path: str, name: str = ''):
        try:
            if (os.stat(path)[0] & 0x4000) != 0:
                self.hashmap['static'][name if name != '' else path] = path
            else:
                raise NotADirectoryError()
        except:
            raise Exception(f'"{path}" is not a valid directory!')
    
    def http(self, methods: str|int, pattern: str = ''):
        def decorator(callback: callable) -> callable[[HTTP], int]:
            self.hashmap['http'][pattern] = (list(map(lambda s: s.strip(), methods.upper().split('|'))), callback)

        return decorator

    def status(self, status_code: int):
        def decorator(callback: callable) -> callable[[HTTP], int]:
            self.hashmap['status'][int(status_code)] = callback

        return decorator
    
    def websocket(self, port: int):
        def decorator(callback: callable) -> callable[[Websocket],]:
            self.hashmap['websocket'][int(port)] = callback

        return decorator

    async def send(self, writer: asyncio.StreamWriter, http: HTTP, status_code: int):
        led.value(1)

        try:
            headers = [f'HTTP/1.1 {status_code}']
            http.response.content_headers['Content-type'] = http.response.content_type

            for name, content in http.response.content_headers.items():
                headers.append(f'{name}: {content}')
                
            writer.write(bytes('\r\n'.join(headers) + '\r\n\r\n', 'utf-8'))
            await writer.drain()
            writer.write(bytes(http.response.content, 'utf-8'))
            await writer.drain()
        except Exception as e:
            print(f'RouterHTTP.send("{http.request.url}"): {e}')
        finally:
            writer.close()
            await writer.wait_closed()
            n = time.localtime()
            print(f'{n[0]}/{n[1]:0>2}/{n[2]:0>2} {n[3]:0>2}:{n[4]:0>2}:{n[5]:0>2} - {http.request.method} {status_code} {http.request.url} ({http.response.content_type})')
        
        led.value(0)

    async def __start_webhttp(self, port: int = 80):
        async def client_callback(reader: asyncio.StreamReader, writer: asyncio.asyncioStreamWriter):
            gc.collect()

            try:
                http = HTTP()
                status_code = HTTP.STATUS_NOT_FOUND

                while True:
                    if (line := (await reader.readline()).decode('utf-8').strip()) == '':
                        break

                    if len(http.request.headers) == 0:
                        if (match := re.compile(r'(GET|POST)\s+([^\s]+)\s+HTTP').search(line)):
                            if len(uu := match.group(2).split('?')) == 2:
                                for pp in uu[1].split('&'):
                                    if len(p := pp.split('=')) == 2:
                                        http.request.params[url_decode(p[0])] = url_decode(p[1])

                            http.request.url = uu[0]
                            http.request.method = match.group(1)
                    
                    if len(splitted_line := line.split(': ')) == 2:
                        http.request.headers[str(splitted_line[0]).lower()] = splitted_line[1]

                if not http.request.url:
                    return
                
                if http.request.method == 'POST':            
                    try:
                        if (content_length := int(http.request.headers['content-length'])) > 0:
                            post_data = await reader.readexactly(content_length)
                    except:
                        return await self.send(writer, http, HTTP.STATUS_LENGTH_REQUIRED)

                    try:
                        content_type = str(http.request.headers['content-type']).lower()

                        if 'application/x-www-form-urlencoded' in content_type:
                            for p in post_data.decode('utf-8').split('&'):
                                k, v = p.split('=')
                                http.request.post_data[url_decode(k)] = url_decode(v)
                        elif 'application/json' in content_type:
                            http.request.post_data = json.loads(post_data)
                        else:
                            raise TypeError()
                    except:
                        return await self.send(writer, http, HTTP.STATUS_UNSUPPORTED_MEDIA_TYPE)
                elif http.request.method == 'GET':
                    for name, path in self.hashmap['static'].items():
                        if http.request.url.startswith(name):
                            try:
                                if ((stat := os.stat(filename := f'{path}{http.request.url[len(name):]}'))[0] & 0x4000) == 0:
                                    with open(filename, 'rb') as fh:
                                        http.response.content = fh.read()
                                        http.response.content_type = HTTP.HEADER_CONTENT_TYPE.get(filename.lower().split('.')[-1], 'application/octet-stream')
                                        http.response.content_headers['Content-Length'] = stat[6]
                                        status_code = HTTP.STATUS_OK
                                else:
                                    raise FileNotFoundError()
                            except:
                                status_code = HTTP.STATUS_NOT_FOUND

                                if status_code in self.hashmap['status']:
                                    self.hashmap['status'][status_code](http)

                            return await self.send(writer, http, status_code)

                for pattern, item in self.hashmap['http'].items():
                    if http.request.method not in item[0]:
                        continue

                    if pattern == http.request.url or (match := re.match('^' + pattern + '$', http.request.url)):
                        args = []
                        
                        if match:
                            args = [i for i in match.groups() if i is not None]

                        status_code = item[1](http, *args) or HTTP.STATUS_NO_CONTENT

                if status_code in self.hashmap['status']:
                    self.hashmap['status'][status_code](http)

                return await self.send(writer, http, status_code)
            except OSError as e:
                print(f'RouterHTTP.client_callback(): {e}')
                writer.close()
            
        shutdown_event = asyncio.Event()

        async with (server := await asyncio.start_server(client_callback, self.ifconfig[0], port)):
            await shutdown_event.wait()

    async def __start_websocket(self, port: int, callback: callable):
        def handshake(sock: socket.socket):
            if (client := self.__websocket_handshake(sock)):
                loop = asyncio.get_event_loop()
                loop.create_task(callback(client))

        sock: socket.socket = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', port))
        sock.listen(1)
        sock.setsockopt(socket.SOL_SOCKET, 20, handshake)

        for i in [network.STA_IF, network.AP_IF]:
            if network.WLAN(i).active():
                print(f'$ WebSocket started on ws://{self.ifconfig[0]}:{port}')
                break
        else:
            raise Exception(f'$ Unable to start WebSocket on ws://{self.ifconfig[0]}:{port}')

        # keep coroutine alive
        await Websocket.close_dead_sockets()
        
    def __websocket_handshake(self, sock: socket.socket) -> Websocket:
        client, address = sock.accept()

        if Websocket.is_enough():
            print('Connection refused:', str(address))
            client.setblocking(True)
            client.send(b'HTTP/1.1 503 Too many connections\r\n')
            client.send(b'\r\n\r\n')
            time.sleep(1)
            
            return client.close()

        try:
            connection = Websocket(client, address)
            stream = client.makefile('rwb', 0)
            time.sleep(0.25)
            line = stream.readline()

            while True:
                if not (line := stream.readline()) or line == b'\r\n':
                    break

                h, v = [x.strip().decode() for x in line.split(b':', 1)]
                connection.headers[h] = v

            if not connection.token:
                raise Exception(f'"Sec-WebSocket-Key" not found in client<{address}>\'s headers!')
            
            headers = [
                'HTTP/1.1 101 Switching Protocols', 
                'Upgrade: websocket', 
                'Connection: Upgrade', 
                f'Sec-WebSocket-Accept: {connection.token_digest}'
            ]
            client.send(bytes('\r\n'.join(headers) + '\r\n\r\n', 'utf-8'))
            connection.open()
            
            return connection
        except Exception as e:
            print(f'WebSocket Exception: {e}')
            client.close()

    def listen(self, port: int = 80):
        async def serve_forever():
            await asyncio.gather(self.__start_webhttp(port), *[self.__start_websocket(a, b) for a, b in self.hashmap['websocket'].items()])
        
        asyncio.run(serve_forever())


