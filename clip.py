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

# Detect if it's host or guest
if sys.argv[1] == "host":
  isHost = True
elif sys.argv[1] == "guest":
  isHost = False
else:
  print("Please indicate if guest or host")
  sys.exit(1)

otherString = "guest" if isHost else "host"

# Argument parser
parser =  argparse.ArgumentParser()
parser.add_argument('-a', dest='address', type=str, default=ADDR, nargs='?')
parser.add_argument('-p', dest='port', type=int, default=PORT, nargs='?')
parser.add_argument('-b', dest='bytesize', type=int, default=BYTESIZE, nargs='?')
args = vars(parser.parse_args(sys.argv[2:]))

# useful globals
inbound = outbound = None
justReceived = False

# Qt Gui Application for reading and writing to the clipboard
app = QGuiApplication([])

# this function will monitor changes in the clipboard
def clipboardChanged():
  global outbound, justReceived

  # clipboard changed because we received an update from host/guest
  if justReceived:
    justReceived = False
    return
  
  # read the clipboard
  readClip = app.clipboard().mimeData()

  # dict to store elements of the clipboard
  clipObj = {
    'image': None,
    'html': None,
    'text': None
  }

  if readClip.hasImage():
    # we can only send bytes-like objects. store the image in a byte array
    # and encode it in base 64
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
    # maybe add support for more data types? color, urls..
    print("Clipboard changed but no data type is supported")
    return

  print("Clipboard changed, sending <{}> to {}".format(
    str([key for key, val in clipObj.items() if val is not None])[1:-1],
    otherString
  ))

  serialized = base64.b64encode(pickle.dumps(clipObj)).decode('utf-8')
  # store information in the outbound global so the looping function will send it
  outbound = ("{}:{}".format(len(serialized), serialized)).encode('utf-8')

def checkInbound():
  global inbound, justReceived

  # check if we have received data from the host/guest
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
    # we need to decode the image and get it from the bytearray
    byteArray = base64.b64decode(clipObj['image'].encode('utf-8'))
    image = QImage()
    image.loadFromData(byteArray, "PNG")
    mimeData.setImageData(image)
  
  if 'html' in dataTypes:
    mimeData.setHtml(clipObj['html'])

  if 'text' in dataTypes:
    mimeData.setText(clipObj['text'])
    
  justReceived = True
  app.clipboard().setMimeData(mimeData) # update the clipboard

def exitHandler(sig = None, frame = None, conn = None):
  if conn is not None:
    conn.close()
  print('Disconnected')
  app.quit()
  sys.exit(0)

def loop(conn):
  global inbound, outbound

  while True:
    # check if host/guest has sent data
    readable, _, _ = select.select([conn], [], [], RECEIVE_TIMEOUT)

    if not readable:
      # as the host/guest didn't receive data, we check if there's any
      # information in the outbound global and send it (clipboard changed)
      if outbound is not None:
        conn.sendall(outbound)
        outbound = None
      
      continue

   # some helper variables
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
        # we have started to receive data
        buffer += decodedData

        if len(buffer) >= size:
          # we have finished to receive data, time to put it in the inbound
          # global
          inbound = buffer.encode('utf-8')
          break
      else:
        if ':' in decodedData:
          # format of every message between the host and guest
          # size:data
          # we look for the colon to know how long every message is
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
  # host needs to initialize the server, wait for the guest and then go into
  # the loop
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
  # guest needs to connect to the server and then go into the loop
  serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  serv.connect((args['address'], args['port']))

  print("Established connection with {}".format(otherString))
  loop(serv)

# every time clipboard changes, clipboardChanged() will be called
app.clipboard().dataChanged.connect(clipboardChanged)

# we need to call host() or guest(), it needs to run on a separate thread
# so it will not hang the entire main thread
loopThread = threading.Thread(target=host if isHost else guest, daemon=True)
loopThread.start()

# this timer will trigger checkInbound periodically
timer = QtCore.QTimer()
timer.timeout.connect(checkInbound)
timer.start(int(RECEIVE_TIMER * 1000))

# run exitHandler on SIGINT and start the QGuiApplication loop
signal.signal(signal.SIGINT, exitHandler)
app.exec_()