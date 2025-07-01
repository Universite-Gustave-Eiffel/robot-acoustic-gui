import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QLineEdit, QPushButton


class MyWindow(QWidget):

    def __init__(self, win):
        super().__init__()
        self.win = win

    def changeColor(self, color):
        self.win.setStyleSheet(f"background-color: {color};")


    def textChange(self):
        textLine = self.lineEdit.text()
        print(textLine)

    def buttonPressed(self):
        print("Button Pressed")


    def build(self):
        self.win.setWindowTitle("My Window")
        self.win.setGeometry(100, 100, 600, 400)

        #create QLabel
        self.label = QLabel("Coucou!", self.win)
        self.label.setGeometry(50, 50, 200, 50)
        self.label.setStyleSheet("background-color: red; color: white; font-size: 20px;")
        self.label.setAlignment(Qt.AlignCenter)

        #create QLineEdit
        self.lineEdit = QLineEdit(self.win)
        self.lineEdit.setGeometry(50, 150, 200, 50)
        self.lineEdit.setStyleSheet("background-color: blue; color: white; font-size: 20px;")
        self.lineEdit.textChanged.connect(self.textChange)

        #create QPushButton
        self.button = QPushButton("Click Me!", self.win)
        self.button.setGeometry(50, 250, 200, 50)
        self.button.setStyleSheet("background-color: green; color: white; font-size: 20px;")
        self.button.clicked.connect(self.buttonPressed)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    root = QWidget()
    window = MyWindow(root)
    window.build()
    window.changeColor("#17657D")
    root.show()
    sys.exit(app.exec_())