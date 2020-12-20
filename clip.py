import socket
import sys
import threading
from PyQt5.QtGui import QGuiApplication, QImage
from PyQt5 import QtCore
import signal
import select
import pickle
import argparse
import threading
import base64

# Defaults
ADDR = '127.0.0.1'
PORT = 12000
BYTESIZE = 1 << 12
RECEIVE_TIMEOUT = 0.5
RECEIVE_TIMER = 0.1

if sys.argv[1] == "host":
  isHost = True
elif sys.argv[1] == "guest":
  isHost = False
else:
  print("Please indicate if guest or host")
  sys.exit(1)

otherString = "guest" if isHost else "host"

parser =  argparse.ArgumentParser()
parser.add_argument('-a', dest='address', type=str, default=ADDR, nargs='?')
parser.add_argument('-p', dest='port', type=int, default=PORT, nargs='?')
parser.add_argument('-b', dest='bytesize', type=int, default=BYTESIZE, nargs='?')
args = vars(parser.parse_args(sys.argv[2:]))

inbound = outbound = None
justReceived = False
validTypes = [""]

app = QGuiApplication([])

def clipboardChanged():
  global outbound, justReceived

  if justReceived:
    justReceived = False
    return
  
  readClip = app.clipboard().mimeData()

  clipObj = {
    'image': None,
    'html': None,
    'text': None
  }

  if readClip.hasImage():
    byteArray = QtCore.QByteArray()
    buffer = QtCore.QBuffer(byteArray)
    buffer.open(QtCore.QIODevice.WriteOnly)
    readClip.imageData().save(buffer, "PNG")
    clipObj['image'] = base64.b64encode(byteArray).decode('utf-8')
  
  if readClip.hasHtml():
    clipObj['html'] = readClip.html()
  
  if readClip.hasText():
    clipObj['text'] = readClip.text()

  if all(val is None for val in clipObj):
    print("Clipboard changed but no data type is supported")
    return

  print("Clipboard changed, sending <{}> to {}".format(
    str([key for key, val in clipObj.items() if val is not None])[1:-1],
    otherString
  ))

  serialized = base64.b64encode(pickle.dumps(clipObj)).decode('utf-8')
  outbound = ("{}:{}".format(len(serialized), serialized)).encode('utf-8')

def checkInbound():
  global inbound, justReceived

  if inbound is None:
    return

  data = inbound
  inbound = None

  clipObj = pickle.loads(base64.b64decode(data))
  mimeData = QtCore.QMimeData()
  dataTypes = [key for key, val in clipObj.items() if val is not None]

  print("Received <{}> from {}. Copying to clipboard.".format(
    str(dataTypes)[1:-1], otherString))

  if 'image' in dataTypes:
    byteArray = base64.b64decode(clipObj['image'].encode('utf-8'))
    image = QImage()
    image.loadFromData(byteArray, "PNG")
    mimeData.setImageData(image)
  
  if 'html' in dataTypes:
    mimeData.setHtml(clipObj['html'])

  if 'text' in dataTypes:
    mimeData.setText(clipObj['text'])
    
  justReceived = True
  app.clipboard().setMimeData(mimeData)

def exitHandler(sig = None, frame = None, conn = None):
  if conn is not None:
    conn.close()
  print('Disconnected')
  app.quit()
  sys.exit(0)

def loop(conn):
  global inbound, outbound

  while True:
    readable, _, _ = select.select([conn], [], [], RECEIVE_TIMEOUT)

    if not readable:
      if outbound is not None:
        conn.sendall(outbound)
        outbound = None
      
      continue

    receiving = False
    size = 0
    buffer = ''
    
    while True:
      data = conn.recv(args['bytesize'])
      decodedData = data.decode('utf-8')

      if not data:
        # connection is probably broken
        exitHandler(conn=conn)
      
      if receiving:
        buffer += decodedData

        if len(buffer) >= size:
          inbound = buffer.encode('utf-8')
          break
      else:
        if ':' in decodedData:
          size = int(decodedData.split(':', 1)[0])
          buffer = decodedData.split(':', 1)[1]

          if len(buffer) >= size:
            inbound = buffer.encode('utf-8')
            break

          receiving = True
        else:
          print('Invalid message received from {}'.format(otherString))
          break

def host():
  serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  serv.bind((args['address'], args['port']))
  serv.listen()
  print("Server started at {}:{}. Waiting for {}".format(
    args['address'], args['port'], otherString))
  
  conn, addr = serv.accept()

  with conn:
    print("Guest connected at {}".format(addr))
    loop(conn)

def guest():
  serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  serv.connect((args['address'], args['port']))

  print("Established connection with {}".format(otherString))
  loop(serv)

app.clipboard().dataChanged.connect(clipboardChanged)

loopThread = threading.Thread(target=host if isHost else guest, daemon=True)
loopThread.start()

timer = QtCore.QTimer()
timer.timeout.connect(checkInbound)
timer.start(int(RECEIVE_TIMER * 1000))

signal.signal(signal.SIGINT, exitHandler)

app.exec_()














