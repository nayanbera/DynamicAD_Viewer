from pyqtgraph.Qt import QtGui, QtCore, uic, QtTest
import pyqtgraph as pg
import numpy as np
import sys
import os
from scipy.misc import imread, imsave
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
        self.connected = True
        self.detPV=detPV
        self.init_PVs()
        QtTest.QTest.qWait(1000)
        self.sizeX = self.sizeX_PV.value
        self.sizeY = self.sizeY_PV.value
        if self.sizeX is None or self.sizeY is None:
            self.connected=False


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
    posTimeSeriesReady = QtCore.pyqtSignal()
    widTimeSeriesReady = QtCore.pyqtSignal()

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
        detPV, okPressed = QtGui.QInputDialog.getText(self, "Get Detector PV", "Detector PV", QtGui.QLineEdit.Normal,
                                               "15IDPS3:")
        if not okPressed:
            detPV="15IDPS3:"
        self.detPVLineEdit.setText(detPV)
        self.onDetPVChanged()


    def closeEvent(self,evt):
        if self.adReader.connected:
            epics.caput(BYTES2STR(self.detPV + "cam1:Acquire"), 0)
            epics.caput(BYTES2STR(self.detPV + "cam1:ArrayCounter"), 0)
        sys.exit()

    def validateFormat(self):
        self.intValidator=QtGui.QIntValidator()
        self.dblValidator=QtGui.QDoubleValidator()
        self.pixelSizeLineEdit.setValidator(self.dblValidator)

    def init_signals(self):
        self.detPVLineEdit.returnPressed.connect(self.onDetPVChanged)
        self.openImageFilePushButton.clicked.connect(self.openImageFile)

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

        self.posTimeSeriesReady.connect(self.updatePosSeriesPlot)
        self.widTimeSeriesReady.connect(self.updateWidSeriesPlot)


    def onDetPVChanged(self):
        self.detPV=self.detPVLineEdit.text()
        self.adReader=AD_Reader(parent=self,detPV=self.detPV)
        if self.adReader.connected:
            self.horROIWidthSpinBox.setMaximum(self.adReader.sizeX)
            self.verROIWidthSpinBox.setMaximum(self.adReader.sizeY)
            self.ROIWinX=self.horROIWidthSpinBox.value()
            self.ROIWinY=self.verROIWidthSpinBox.value()
            self.create_PlotLayout()
        #    self.init_signals()
            self.imageSizeXLineEdit.setText('%d'%self.adReader.sizeX)
            self.imageSizeYLineEdit.setText('%d'%self.adReader.sizeY)
        else:
            QtGui.QMessageBox.warning(self,"PV Error","Please check the PV is valid and the Detector IOC is running."
                                                      ,QtGui.QMessageBox.Ok)
        self.init_signals()
            #self.close()

    def openImageFile(self):
        fname=QtGui.QFileDialog.getOpenFileName(self,'Select an image file',filter='Image File (*.tif *.tiff)',
                                                directory=self.dataDir)[0]
        if fname is not None and os.path.exists(fname):
            self.create_PlotLayout(image=fname)


    def saveImage(self):
        try:
            data=self.imgData
            fname=QtGui.QFileDialog.getSaveFileName(self,"Save image file as",directory=self.dataDir,filter="Image "
                                                                                                           "File ("
                                                                                                     "*.tif "
                                                                                             "*.tiff)")
            self.dataDir=os.path.dirname(fname[0])
            imsave(fname[0],data.T)
        except:
            QtGui.QMessageBox.warning(self,"Data Error","The 2D data doesnot exist. Please make sure the IOC is "
                                                        "running and at least one image is collected from the "
                                                        "camera.", QtGui.QMessageBox.Ok)
    def saveHorProfile(self):
        try:
            data=np.vstack((self.xValues, self.horCutData))
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
            data=np.vstack((self.yValues, self.verCutData))
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
        x=(right + left) / 2
        self.verLine.setRegion((x - self.ROIWinX * self.pixelSize / 2,x + self.ROIWinX * self.pixelSize/ 2))


    def onROIWinYChanged(self):
        self.ROIWinY=self.verROIWidthSpinBox.value()
        up,down=self.horLine.getRegion()
        y = (up + down) / 2
        self.horLine.setRegion((y - self.ROIWinY * self.pixelSize / 2, y + self.ROIWinY * self.pixelSize / 2))

    def onStartUpdate(self):
        self.cutSeriesExists=False
        self.widSeriesExists=False
        epics.caput(BYTES2STR(self.detPV + "cam1:ArrayCounter"), 0)
        epics.caput(BYTES2STR(self.detPV + "cam1:Acquire"), 1)
        QtTest.QTest.qWait(100)
        self.startUpdate=True
        self.startTime = time.time()
        self.posTimeData = []
        self.widTimeData = []
        self.start_stop_Update()
        self.startUpdatePushButton.setEnabled(False)
        self.stopUpdatePushButton.setEnabled(True)
        self.setOutputOptions(enabled=False)
        self.detPVLineEdit.setEnabled(False)


    def onStopUpdate(self):
        self.startUpdate=False
        self.startUpdatePushButton.setEnabled(True)
        self.stopUpdatePushButton.setEnabled(False)
        self.setOutputOptions(enabled=True)
        self.detPVLineEdit.setEnabled(True)
        epics.caput(BYTES2STR(self.detPV + "cam1:Acquire"), 0)
        epics.caput(BYTES2STR(self.detPV + "cam1:ArrayCounter"),0)
        if self.widSeriesExists:
            self.widthCutPlot.parent().close()
        if self.cutSeriesExists:
            self.peakCutPlot.parent().close()



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


    def create_PlotLayout(self,image=None):
        self.xValues=self.pixelSize*np.arange(self.adReader.sizeX)
        self.yValues=self.pixelSize*np.arange(self.adReader.sizeY)
        #self.vb = self.imageLayout.addViewBox(lockAspect=True)
        self.imagePlot=self.imageLayout.getItem(0,0)
        if self.imagePlot is None:
            self.imagePlot = self.imageLayout.addPlot(title='2D Image')
            self.imagePlot.setLabel('left',text='Y',units='m')
            self.imagePlot.setLabel('bottom',text='X',units='m')
            self.imagePlot.setAspectLocked(lock=True,ratio=1)
        self.imgPlot = pg.ImageItem()
        self.imgPlot.scale(self.pixelSize, self.pixelSize)
        try:
            self.imagePlot.removeItem(self.imgPlot)
        except:
            pass
        self.imagePlot.addItem(self.imgPlot)
        self.vb = self.imagePlot.getViewBox()
        self.vb.scene().sigMouseClicked.connect(self.onClick)
        self.vb.addItem(self.imgPlot)
        self.vb.setRange(QtCore.QRectF(0, 0, self.adReader.sizeX, self.adReader.sizeY))
        if image is None:
            try:
                data = self.adReader.data_PV.get()
                self.imgData = np.rot90(data.reshape(self.adReader.sizeY, self.adReader.sizeX), k=-1, axes=(0, 1))
            except:
                data=imread('2dimage_2.tif')
                self.imgData = np.rot90(data.reshape(self.adReader.sizeY, self.adReader.sizeX), k=-1, axes=(0, 1))
        else:
            data=imread(image)
            self.imgData = np.rot90(data.reshape(self.adReader.sizeY, self.adReader.sizeX), k=-1, axes=(0, 1))
        self.imgPlot.setImage(self.imgData)
        self.verCut=self.verCutLayout.getItem(0,0)
        if self.verCut is None:
            self.verCut=self.verCutLayout.addPlot()#title='Vertical Cut')
#            self.verCut.setLabel('left',text='Y',units='m')
            self.verCut.setLabel('bottom', text='Vertical Cut', units='Cnts')
            self.verCut.hideAxis('left')
#            self.verCut.showAxis('right')
            self.verCut.invertX()
            self.verCut.setYLink(self.vb)
            #self.verCut.autoRange()

        self.horCut=self.horCutLayout.getItem(0,0)
        if self.horCut is None:
            self.horCut=self.horCutLayout.addPlot()#title='Horizontal Cut')
            self.horCut.setLabel('bottom', text='X', units='m')
            self.horCut.hideAxis('bottom')
            self.horCut.setLabel('left', text='Horizontal Cut', units='Cnts')
            self.horCut.setXLink(self.vb)
        left=int(self.adReader.sizeX/2)
        top=int(self.adReader.sizeY/2)
        self.verLine=pg.LinearRegionItem(values=((left - self.ROIWinX/2) * self.pixelSize,
                                                 (left + self.ROIWinX/2) * self.pixelSize),
                                                 orientation=pg.LinearRegionItem.Vertical,bounds=(0,
                                                                                                  self.adReader.sizeX*self.pixelSize))
        self.horLine=pg.LinearRegionItem(values=((top - self.ROIWinX/2) * self.pixelSize,
                                                 (top + self.ROIWinY/2) * self.pixelSize),
                                                 orientation=pg.LinearRegionItem.Horizontal,bounds=(0,
                                                                                                self.adReader.sizeY*self.pixelSize))
        try:
            self.imagePlot.removeItem(self.verLine)
            self.imagePlot.removeItem(self.horLine)
        except:
            pass
        self.imagePlot.addItem(self.verLine)
        self.imagePlot.addItem(self.horLine)
        self.verLine.sigRegionChanged.connect(self.onVerLineChanged)
        self.horLine.sigRegionChanged.connect(self.onHorLineChanged)
        self.onVerLineChanged()
        self.onHorLineChanged()
        self.updatePlots()
        self.imagePlot.setRange(xRange=(self.xValues[0], self.xValues[-1]), yRange = (self.yValues[0], self.yValues[
            -1]))
        self.imagePlot.setLimits(xMin = self.xValues[0], xMax=self.xValues[-1], yMin = self.yValues[0],
                                 yMax = self.yValues[
            -1])
        self.verCut.setLimits(yMin = self.yValues[0],
                                 yMax = self.yValues[
            -1])
        # self.verSum.setLimits(yMin=self.yValues[0],
        #                       yMax=self.yValues[
        #                           -1])
        self.horCut.setLimits(xMin=self.xValues[0],
                              xMax=self.xValues[
                                  -1])
        # self.horSum.setLimits(xMin=self.xValues[0],
        #                       xMax=self.xValues[
        #                           -1])

        # self.timePosSeries=self.timeSeriesPosLayout.getItem(0,0)
        # if self.timePosSeries is None:
        #     self.timePosSeries=self.timeSeriesPosLayout.addPlot(title='Peak Positions')
        #     self.timePosSeries.setLabel('left','X, Y Pos', units='m')
        #     self.timePosSeries.setLabel('bottom','time',units='sec')
        #
        # self.timeWidSeries=self.timeSeriesWidLayout.getItem(0,0)
        # if self.timeWidSeries is None:
        #     self.timeWidSeries=self.timeSeriesWidLayout.addPlot(title='Peak Widths')
        #     self.timeWidSeries.setLabel('left', 'X, Y Wid', units='m')
        #     self.timeWidSeries.setLabel('bottom', 'time', units='sec')

    def onClick(self,evt):
        pos=self.vb.mapSceneToView(evt.scenePos())
        x,y=int(pos.x()/self.pixelSize),int(pos.y()/self.pixelSize)
        if 0<=x<self.adReader.sizeX and 0<=y<self.adReader.sizeY:
            self.verLine.setRegion(((x - self.ROIWinX / 2) * self.pixelSize, (x + self.ROIWinX / 2) * self.pixelSize))
            self.horLine.setRegion(((y - self.ROIWinY / 2) * self.pixelSize, (y + self.ROIWinY / 2) * self.pixelSize))


    def onVerLineChanged(self):
        left,right=self.verLine.getRegion()
        self.left,self.right=int(left/self.pixelSize),int(right/self.pixelSize)
        val=np.abs(self.right-self.left)
        if np.mod(val,2)==0:
            self.horROIWidthSpinBox.setValue(val)
        self.updateVerCut()


    def onHorLineChanged(self):
        up,down=self.horLine.getRegion()
        self.up,self.down=int(up/self.pixelSize),int(down/self.pixelSize)
        val=np.abs(self.up-self.down)
        if np.mod(val,2)==0:
            self.verROIWidthSpinBox.setValue(val)
        self.updateHorCut()

    def updateVerCut(self):
        self.verCutData=np.sum(self.imgData[int(self.left):int(self.right),:],axis=0)
        try:
            self.verCutPlot.setData(self.verCutData,self.yValues)
        except:
            self.verCutPlot=self.verCut.plot(self.verCutData,self.yValues, pen=pg.mkPen('y'))
        verCut = self.verCutData - np.min(self.verCutData)
        self.cutPeakY = np.sum(verCut * self.yValues) / np.sum(verCut)
        cutY = np.argwhere(verCut >= np.max(verCut) / 2.0)
        self.cutWidthY = np.abs(self.yValues[cutY[0]] - self.yValues[cutY[-1]])
        self.verCut.setTitle("Peak=%.4f, Wid=%.4f" % (1e3 * self.cutPeakY, 1e3 * self.cutWidthY))
        #self.verCut.setXRange(0,np.max(verCut))

    def updateHorCut(self):
        self.horCutData=np.sum(self.imgData[:,int(self.up):int(self.down)],axis=1)
        try:
            self.horCutPlot.setData(self.xValues,self.horCutData)
        except:
            self.horCutPlot=self.horCut.plot(self.xValues,self.horCutData, pen=pg.mkPen('b'))
        horCut = self.horCutData - np.min(self.horCutData)
        self.cutPeakX = np.sum(horCut * self.xValues) / np.sum(horCut)
        cutX = np.argwhere(horCut >= np.max(horCut) / 2.0)
        self.cutWidthX = np.abs(self.xValues[cutX[0]] - self.xValues[cutX[-1]])
        self.horCut.setTitle("Peak=%.4f, Wid=%.4f" % (1e3 * self.cutPeakX, 1e3 * self.cutWidthX))

    def updatePlots(self):
#        self.updateSums()
        self.updateVerCut()
        self.updateHorCut()
        if self.plotPosCheckBox.isChecked():
            t = time.time() - self.startTime
            self.posTimeData.append([t, self.cutPeakX, self.cutPeakY])
            if len(self.posTimeData)>100:
                self.posTimeData.pop(0)
                self.posTimeSeriesReady.emit()
        if self.plotWidCheckBox.isChecked():
            t = time.time() - self.startTime
            self.widTimeData.append([t, self.cutWidthX, self.cutWidthY])
            if len(self.widTimeData)>100:
                self.widTimeData.pop(0)
                self.widTimeSeriesReady.emit()
        QtGui.QApplication.processEvents()

    def updatePosSeriesPlot(self):
        posData=np.array(self.posTimeData)
        x = posData[:,0] - posData[0, 0]
        if self.cutSeriesExists:
            self.peakCutXPlot.setData(x, posData[:, 1])
            self.peakCutYPlot.setData(x, posData[:, 2])
        else:
            self.peakCutPlot=pg.plot(title = 'Peak-Poistion Plot')
            self.peakCutPlot.parent().closeEvent=self.peakCutPlotCloseEvent
            self.peakCutPlot.setLabel('left','X, Y Positions', units='m')
            self.peakCutPlot.setLabel('bottom','time',units='seconds')
            self.peakCutXPlot=pg.PlotCurveItem(x, posData[:, 1],name='cut X',
                                                      pen=pg.mkPen('b'), title='X-Cut Plot')
            self.peakCutYPlot=pg.PlotCurveItem(x, posData[:, 2], name='cut Y',
                                                      pen=pg.mkPen('y'), title='Y-Cut Plot')
            self.peakCutPlot.addItem(self.peakCutXPlot)
            self.peakCutPlot.addItem(self.peakCutYPlot)
            self.cutSeriesExists=True

    def peakCutPlotCloseEvent(self,evt):
        self.cutSeriesExists=False


    def updateWidSeriesPlot(self):
        widData = np.array(self.widTimeData)
        x = widData[:, 0] - widData[0, 0]
        if self.widSeriesExists:
            self.widthCutXPlot.setData(x, widData[:, 1])
            self.widthCutYPlot.setData(x, widData[:, 2])
            # self.widthCutYPlot.setData(x, widData[:, 4])
        else:
            self.widthCutPlot = pg.plot(title='Peak-Width Plot')
            self.widthCutPlot.parent().closeEvent=self.widthCutPlotCloseEvent
            self.widthCutPlot.setLabel('left','X, Y Widths',units='m')
            self.widthCutPlot.setLabel('bottom','time',units='seconds')
            self.widthCutXPlot=pg.PlotCurveItem(x, widData[:, 1], name='wid X', pen=pg.mkPen('b'),)
            self.widthCutYPlot=pg.PlotCurveItem(x, widData[:, 2], name='wid Y', pen=pg.mkPen('y'))
            self.widthCutPlot.addItem(self.widthCutXPlot)
            self.widthCutPlot.addItem(self.widthCutYPlot)
            self.widSeriesExists=True

    def widthCutPlotCloseEvent(self,evt):
        self.widSeriesExists = False





    # def updateSums(self):
    #     self.verSumData=np.sum(self.imgData,axis=0)
    #     self.horSumData=np.sum(self.imgData,axis=1)
    #     try:
    #         self.verSumPlot.setData(self.verSumData,self.yValues)
    #         self.horSumPlot.setData(self.xValues,self.horSumData)
    #     except:
    #         self.verSumPlot=self.verSum.plot(self.verSumData,self.yValues, pen=pg.mkPen('g'))
    #         self.horSumPlot=self.horSum.plot(self.xValues,self.horSumData, pen=pg.mkPen('r'))
    #     horSum = self.horSumData - np.min(self.horSumData)
    #     verSum = self.verSumData - np.min(self.verSumData)
    #     self.sumPeakX = np.sum(horSum * self.xValues) / np.sum(horSum)
    #     self.sumPeakY = np.sum(verSum * self.yValues) / np.sum(verSum)
    #     peakX=np.argwhere(horSum>=np.max(horSum)/2.0)
    #     peakY=np.argwhere(verSum>=np.max(verSum)/2.0)
    #     self.sumWidthX=np.abs(self.xValues[peakX[0]]-self.xValues[peakX[-1]])
    #     self.sumWidthY = np.abs(self.yValues[peakY[0]] - self.yValues[peakY[-1]])
    #     self.horSum.setTitle("Peak=%.4f, Wid=%.4f" % (1e3 * self.sumPeakX, 1e3 * self.sumWidthX))
    #     self.verSum.setTitle("Peak=%.4f, Wid=%.4f" % (1e3 * self.sumPeakY, 1e3 * self.sumWidthY))
        #QtGui.QApplication.processEvents()


## Start Qt event loop unless running in interactive mode.
if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    w = DynamicAD_Viewer()
    w.setWindowTitle('Dynamic Area Detector Viewer')
    w.resize(1200,800)
    #w.show()
    sys.exit(app.exec_())