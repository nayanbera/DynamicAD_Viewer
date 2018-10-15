from pyqtgraph.Qt import QtGui, QtCore, uic, QtTest
import pyqtgraph as pg
import numpy as np
import sys
import os
import copy
from scipy.misc import imread, imsave
import shutil
import epics
from epics.utils import BYTES2STR
import time


class AD_Reader(QtCore.QObject):
    imageSizeXChanged=QtCore.pyqtSignal(int)
    imageSizeYChanged=QtCore.pyqtSignal(int)

    def __init__(self, detPV, parent=None):
        """

        :detPV: Detector PV (example: 15PS1:)
        :param parent:
        """
        QtCore.QObject.__init__(self, parent=parent)
        self.detPV=detPV
        self.init_PVs()
        QtTest.QTest.qWait(1000)
        self.sizeX = self.sizeX_PV.value
        self.sizeY = self.sizeY_PV.value

    def init_PVs(self):
        """
        Initialize all the PVs
        :return:
        """
        self.minX_PV = epics.PV(BYTES2STR(self.detPV+"cam1:MinX_RBV"), callback = self.onMinXChanged)
        self.minY_PV = epics.PV(BYTES2STR(self.detPV+"cam1:MinY_RBV"), callback = self.onMinYChanged)
        self.sizeX_PV = epics.PV(BYTES2STR(self.detPV+"cam1:SizeX_RBV"), callback = self.onSizeXChanged)
        self.sizeY_PV = epics.PV(BYTES2STR(self.detPV+"cam1:SizeY_RBV"), callback = self.onSizeYChanged)
        self.data_PV = epics.PV(BYTES2STR(self.detPV+"image1:ArrayData"))

    def onMinXChanged(self, value, **kwargs):
        self.minX=value
        print("minX changed")

    def onMinYChanged(self, value, **kwargs):
        self.minY=value
        print("minY changed")

    def onSizeXChanged(self, value, **kwargs):
        self.sizeX=value
        self.imageSizeXChanged.emit(value)
        print("sizeX changed")

    def onSizeYChanged(self, value, **kwargs):
        self.sizeY = value
        self.imageSizeYChanged.emit(value)
        print("sizeY changed")




class DynamicAD_Viewer(QtGui.QWidget):
    imageUpdated = QtCore.pyqtSignal(np.ndarray)
    def __init__(self, parent = None):
        """
        :param parent:

        """
        QtGui.QWidget.__init__(self,parent=parent)
        uic.loadUi('./UI_Forms/DynamicAD_Viewer.ui',self)
        self.validateFormat()
        self.stopUpdatePushButton.setEnabled(False)
        self.show()
        self.dataDir=os.getcwd()
        self.onPixelSizeChanged()
        self.detPV=self.detPVLineEdit.text()
        try:
            self.adReader=AD_Reader(parent=self,detPV=self.detPV)
            self.horROIWidthSpinBox.setMaximum(self.adReader.sizeX)
            self.verROIWidthSpinBox.setMaximum(self.adReader.sizeY)
            self.ROIWinX=self.horROIWidthSpinBox.value()
            self.ROIWinY=self.verROIWidthSpinBox.value()
            self.create_PlotLayout()
            self.init_signals()
            self.imageSizeXLineEdit.setText('%d'%self.adReader.sizeX)
            self.imageSizeYLineEdit.setText('%d'%self.adReader.sizeY)
        except:
             QtGui.QMessageBox.warning(self,"Connection Error","Please check the Detector IOC is running. Quiting the "
                                                               "software for now.",QtGui.QMessageBox.Ok)
             self.close()

    def validateFormat(self):
        self.intValidator=QtGui.QIntValidator()
        self.dblValidator=QtGui.QDoubleValidator()
        self.pixelSizeLineEdit.setValidator(self.dblValidator)

    def init_signals(self):
        self.imageUpdated.connect(self.updatePlots)
        self.startUpdatePushButton.clicked.connect(self.onStartUpdate)
        self.stopUpdatePushButton.clicked.connect(self.onStopUpdate)
        self.horROIWidthSpinBox.valueChanged.connect(self.onROIWinXChanged)
        self.verROIWidthSpinBox.valueChanged.connect(self.onROIWinYChanged)
        self.adReader.imageSizeXChanged.connect(self.onSizeXChanged)
        self.adReader.imageSizeYChanged.connect(self.onSizeYChanged)
        self.pixelSizeLineEdit.returnPressed.connect(self.onPixelSizeChanged)

        self.saveImagePushButton.clicked.connect(self.saveImage)
        self.saveHorProfilesPushButton.clicked.connect(self.saveHorProfile)
        self.saveVerProfilesPushButton.clicked.connect(self.saveVerProfile)

    def saveImage(self):
        try:
            data=self.imgData
            fname=QtGui.QFileDialog.getSaveFileName(self,"Save image file as",directory=self.dataDir,filter="Image "
                                                                                                           "File ("
                                                                                                     "*.tif "
                                                                                             "*.tiff)")
            self.dataDir=os.path.dirname(fname[0])
            imsave(fname[0],data)
        except:
            QtGui.QMessageBox.warning(self,"Data Error","The 2D data doesnot exist. Please make sure the IOC is "
                                                        "running and at least one image is collected from the "
                                                        "camera.", QtGui.QMessageBox.Ok)
    def saveHorProfile(self):
        try:
            data=np.vstack((self.xValues,self.horSumData,self.horCutData))
            fname = QtGui.QFileDialog.getSaveFileName(self, "Save horizontal profiles file as",
                                                      directory=self.dataDir,
                                                      filter="Data "
                                                             "File ("
                                                             "*.txt "
                                                             "*.dat)")
            header="Data saved on "+time.asctime()+"\n"
            header+="col_names=['X (mm)','Hor_sum','Hor_cut']"
            self.dataDir = os.path.dirname(fname[0])
            np.savetxt(fname[0],data.T,header=header)
        except:
            QtGui.QMessageBox.warning(self, "Data Error", "The horizontal profile do not exist. Please make sure the "
                                                          "IOC is "
                                                          "running and at least one image is collected from the "
                                                          "camera.", QtGui.QMessageBox.Ok)

    def saveVerProfile(self):
        try:
            data=np.vstack((self.yValues,self.verSumData,self.verCutData))
            fname = QtGui.QFileDialog.getSaveFileName(self, "Save vertical profiles file as",
                                                      directory=self.dataDir,
                                                      filter="Data "
                                                             "File ("
                                                             "*.txt "
                                                             "*.dat)")
            header="Data saved on "+time.asctime()+"\n"
            header+="#col_names=['Y (mm)','Ver_sum','Ver_cut']"
            self.dataDir = os.path.dirname(fname[0])
            np.savetxt(fname[0],data.T,header=header)
        except:
            QtGui.QMessageBox.warning(self, "Data Error", "The vertical profiles do exist. Please make sure the "
                                                          "IOC is "
                                                          "running and at least one image is collected from the "
                                                          "camera.", QtGui.QMessageBox.Ok)

    def onPixelSizeChanged(self):
        self.pixelSize=float(self.pixelSizeLineEdit.text())*1e-6


    def onSizeXChanged(self,value):
        self.imageSizeXLineEdit.setText('%d'%value)

    def onSizeYChanged(self,value):
        self.imageSizeYLineEdit.setText('%d'%value)

    def onROIWinXChanged(self):
        self.ROIWinX=self.horROIWidthSpinBox.value()
        left,right=self.verLine.getRegion()
        x=int((right + left) / 2)
        self.verLine.setRegion((x - self.ROIWinX / 2,x + self.ROIWinX / 2))


    def onROIWinYChanged(self):
        self.ROIWinY=self.verROIWidthSpinBox.value()
        up,down=self.horLine.getRegion()
        y = int((up + down) / 2)
        self.horLine.setRegion((y - self.ROIWinY / 2, y + self.ROIWinY / 2))

    def onStartUpdate(self):
        self.startUpdate=True
        self.start_stop_Update()
        self.startUpdatePushButton.setEnabled(False)
        self.stopUpdatePushButton.setEnabled(True)
        self.setOutputOptions(enabled=False)
        self.detPVLineEdit.setEnabled(False)
        epics.caput(BYTES2STR(self.detPV + "cam1:ArrayCounter"), 0)
        epics.caput(BYTES2STR(self.detPV + "cam1:Acquire"),1)

    def onStopUpdate(self):
        self.startUpdate=False
        self.startUpdatePushButton.setEnabled(True)
        self.stopUpdatePushButton.setEnabled(False)
        self.setOutputOptions(enabled=True)
        self.detPVLineEdit.setEnabled(True)
        epics.caput(BYTES2STR(self.detPV + "cam1:Acquire"), 0)
        epics.caput(BYTES2STR(self.detPV + "cam1:ArrayCounter"),0)


    def setOutputOptions(self,enabled=True):
        self.saveImagePushButton.setEnabled(enabled)
        self.saveHorProfilesPushButton.setEnabled(enabled)
        self.saveVerProfilesPushButton.setEnabled(enabled)

    def start_stop_Update(self):
        if self.startUpdate:
            data=self.adReader.data_PV.get()
            self.imgData=np.rot90(data.reshape(self.adReader.sizeY,self.adReader.sizeX),k=-1,axes=(0,1))
            self.imgPlot.setImage(self.imgData)
            self.imageUpdated.emit(self.imgData)
            QtCore.QTimer.singleShot(0,self.start_stop_Update)
        else:
            return
        #QtGui.QApplication.processEvents()


    def create_PlotLayout(self):
        self.xValues=self.pixelSize*np.arange(self.adReader.sizeX)
        self.yValues=self.pixelSize*np.arange(self.adReader.sizeY)
        #self.vb = self.imageLayout.addViewBox(lockAspect=True)
        self.imagePlot=self.imageLayout.addPlot(self.imagePlot)
        self.imgPlot = pg.ImageItem(border='w')
        self.imagePlot.addItem(self.imgPlot)
        self.vb=self.imagePlot.getViewBox()
        self.vb.scene().sigMouseClicked.connect(self.onClick)
        self.vb.addItem(self.imgPlot)
        self.vb.setRange(QtCore.QRectF(0, 0, self.adReader.sizeX, self.adReader.sizeY))
        data = self.adReader.data_PV.get()
        self.imgData = np.rot90(data.reshape(self.adReader.sizeY, self.adReader.sizeX), k=-1, axes=(0, 1))
        self.imgPlot.setImage(self.imgData)
        self.verSum=self.verSumLayout.addPlot()#title='Vertical Sum')
        self.verSum.setLabel('left',text='Y',units='m')
        self.verSum.setLabel('bottom',text='Vertical Sum')
        self.horSum=self.horSumLayout.addPlot()#title='Horizontal Sum')
        self.horSum.setLabel('bottom',text='X',units='m')
        self.horSum.setLabel('left', text='Horizontal Sum')
        self.verCut=self.verCutLayout.addPlot()#title='Vertical Cut')
        self.verCut.setLabel('left',text='Y',units='m')
        self.verCut.setLabel('bottom', text='Vertical Cut')
        self.horCut=self.horCutLayout.addPlot()#title='Horizontal Cut')
        self.horCut.setLabel('bottom', text='X', units='m')
        self.horCut.setLabel('left', text='Horizontal Cut')
        left=int(self.adReader.sizeX/2)
        top=int(self.adReader.sizeY/2)
        self.verLine=pg.LinearRegionItem(values=(left-self.ROIWinX/2,left+self.ROIWinX/2),orientation=pg.LinearRegionItem.Vertical,bounds=(0,self.adReader.sizeX))
        self.horLine=pg.LinearRegionItem(values=(top-self.ROIWinX/2,top+self.ROIWinY/2),orientation=pg.LinearRegionItem.Horizontal,bounds=(0,self.adReader.sizeY))
        self.vb.addItem(self.verLine)
        self.vb.addItem(self.horLine)
        self.verLine.sigRegionChanged.connect(self.onVerLineChanged)
        self.horLine.sigRegionChanged.connect(self.onHorLineChanged)
        self.onVerLineChanged()
        self.onHorLineChanged()
        self.updatePlots()

    def onClick(self,evt):
        pos=self.vb.mapSceneToView(evt.scenePos())
        x,y=int(pos.x()),int(pos.y())
        if 0<=x<self.adReader.sizeX and 0<=y<self.adReader.sizeY:
            self.verLine.setRegion((x-self.ROIWinX/2,x+self.ROIWinX/2))
            self.horLine.setRegion((y-self.ROIWinY/2,y+self.ROIWinY/2))


    def onVerLineChanged(self):
        self.left,self.right=self.verLine.getRegion()
        self.updateVerCut()


    def onHorLineChanged(self):
        self.up,self.down=self.horLine.getRegion()
        self.updateHorCut()

    def updateVerCut(self):
        self.verCutData=np.sum(self.imgData[int(self.left):int(self.right),:],axis=0)
        try:
            self.verCutPlot.setData(self.verCutData,self.yValues)
        except:
            self.verCutPlot=self.verCut.plot(self.verCutData,self.yValues)
        verCut = self.verCutData - np.min(self.verCutData)
        self.cutPeakY = np.sum(verCut * self.yValues) / np.sum(verCut)
        self.cutWidthY = np.sqrt(
            np.sum(verCut * (self.yValues - self.cutPeakY) ** 2) / 2 / np.sum(verCut))
        self.verCut.setTitle("Peak=%.4f, Wid=%.4f" % (1e3 * self.cutPeakY, 1e3 * self.cutWidthY))

    def updateHorCut(self):
        self.horCutData=np.sum(self.imgData[:,int(self.up):int(self.down)],axis=1)
        try:
            self.horCutPlot.setData(self.xValues,self.horCutData)
        except:
            self.horCutPlot=self.horCut.plot(self.xValues,self.horCutData)
        horCut = self.horCutData - np.min(self.horCutData)
        self.cutPeakX = np.sum(horCut * self.xValues) / np.sum(horCut)
        self.cutWidthX = np.sqrt(
            np.sum(horCut * (self.xValues - self.cutPeakX) ** 2) / 2 / np.sum(horCut))
        self.horCut.setTitle("Peak=%.4f, Wid=%.4f" % (1e3 * self.cutPeakX, 1e3 * self.cutWidthX))

    def updatePlots(self):
        self.updateSums()
        self.updateVerCut()
        self.updateHorCut()




    def updateSums(self):
        self.verSumData=np.sum(self.imgData,axis=0)
        self.horSumData=np.sum(self.imgData,axis=1)
        try:
            self.verSumPlot.setData(self.verSumData,self.yValues)
            self.horSumPlot.setData(self.xValues,self.horSumData)
        except:
            self.verSumPlot=self.verSum.plot(self.verSumData,self.yValues)
            self.horSumPlot=self.horSum.plot(self.xValues,self.horSumData)
        horSum = self.horSumData - np.min(self.horSumData)
        verSum = self.verSumData - np.min(self.verSumData)
        self.sumPeakX = np.sum(horSum * self.xValues) / np.sum(horSum)
        self.sumPeakY = np.sum(verSum * self.yValues) / np.sum(verSum)
        self.sumWidthX = np.sqrt(np.sum(horSum * (self.xValues - self.sumPeakX) ** 2) / 2 / np.sum(horSum))
        self.sumWidthY = np.sqrt(
            np.sum(verSum * (self.yValues - self.sumPeakY) ** 2) / 2 / np.sum(verSum))
        self.horSum.setTitle("Peak=%.4f, Wid=%.4f" % (1e3 * self.sumPeakX, 1e3 * self.sumWidthX))
        self.verSum.setTitle("Peak=%.4f, Wid=%.4f" % (1e3 * self.sumPeakY, 1e3 * self.sumWidthY))
        #QtGui.QApplication.processEvents()














# ## Title at top
# text = """
# This example demonstrates the use of GraphicsLayout to arrange items in a grid.<br>
# The items added to the layout must be subclasses of QGraphicsWidget (this includes <br>
# PlotItem, ViewBox, LabelItem, and GraphicsLayout itself).
# """
# l.addLabel(text, col=1, colspan=4)
# l.nextRow()
#
# ## Put vertical label on left side
# l.addLabel('Long Vertical Label', angle=-90, rowspan=3)
#
# ## Add 3 plots into the first row (automatic position)
# p1 = l.addPlot(title="Plot 1")
# p2 = l.addPlot(title="Plot 2")
# vb = l.addViewBox(lockAspect=True)
# img = pg.ImageItem(np.random.normal(size=(100,100)))
# vb.addItem(img)
# vb.autoRange()
#
#
# ## Add a sub-layout into the second row (automatic position)
# ## The added item should avoid the first column, which is already filled
# l.nextRow()
# l2 = l.addLayout(colspan=3, border=(50,0,0))
# l2.setContentsMargins(10, 10, 10, 10)
# l2.addLabel("Sub-layout: this layout demonstrates the use of shared axes and axis labels", colspan=3)
# l2.nextRow()
# l2.addLabel('Vertical Axis Label', angle=-90, rowspan=2)
# p21 = l2.addPlot()
# p22 = l2.addPlot()
# l2.nextRow()
# p23 = l2.addPlot()
# p24 = l2.addPlot()
# l2.nextRow()
# l2.addLabel("HorizontalAxisLabel", col=1, colspan=2)
#
# ## hide axes on some plots
# p21.hideAxis('bottom')
# p22.hideAxis('bottom')
# p22.hideAxis('left')
# p24.hideAxis('left')
# p21.hideButtons()
# p22.hideButtons()
# p23.hideButtons()
# p24.hideButtons()
#
#
# ## Add 2 more plots into the third row (manual position)
# p4 = l.addPlot(row=3, col=1)
# p5 = l.addPlot(row=3, col=2, colspan=2)
#
# ## show some content in the plots
# p1.plot([1,3,2,4,3,5])
# p2.plot([1,3,2,4,3,5])
# p4.plot([1,3,2,4,3,5])
# p5.plot([1,3,2,4,3,5])



## Start Qt event loop unless running in interactive mode.
if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    w = DynamicAD_Viewer()
    w.setWindowTitle('Dynamic Area Detector Viewer')
    w.resize(1200,800)
    sys.exit(app.exec_())