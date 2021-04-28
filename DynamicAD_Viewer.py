from pyqtgraph.Qt import QtGui, QtCore, uic, QtTest
import pyqtgraph as pg
from PyQt5.Qt import Qt
import numpy as np
import sys
import os
from imageio import imread, imsave
import epics
from epics.utils import BYTES2STR
import time
from itertools import cycle
import copy
import time
from numba import jit

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
        # print("minX changed")

    def onMinYChanged(self, value, **kwargs):
        self.minY=value
        # print("minY changed")

    def onSizeXChanged(self, value, **kwargs):
        self.sizeX=value
        self.imageSizeXChanged.emit(value)
        # print("sizeX changed")

    def onSizeYChanged(self, value, **kwargs):
        self.sizeY = value
        self.imageSizeYChanged.emit(value)
        # print("sizeY changed")




class DynamicAD_Viewer(QtGui.QWidget):
    arrayDataUpdated=QtCore.pyqtSignal()
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
        self.expTime=1.0
        self.period=1.0
        self.floatValidator=QtGui.QDoubleValidator()
        self.expTimeLineEdit.setValidator(self.floatValidator)
        self.acquirePeriodLineEdit.setValidator(self.floatValidator)
        self.startUpdate=False
        self.onPixelSizeChanged()

        detPV, okPressed = QtGui.QInputDialog.getText(self, "Get Detector PV", "Detector PV", QtGui.QLineEdit.Normal,
                                               "15IDPS1:")
        if not okPressed:
            detPV="15IDPS1:"
        self.detPVLineEdit.setText(detPV)
        self.onDetPVChanged()
        self.colorMode = self.colorModeComboBox.currentText()
        self.colorModeChanged()
        self.exposureTimeChanged()
        self.acquirePeriodChanged()
        self.removeCrosshairPushButton.setEnabled(False)
        self.crosshairTableWidget.setEditable(True)
        self.crosshair=[]
        self.colorButtons={}
        self.showCheckBoxes={}
        self.colors=['r', 'g', 'b', 'c', 'm', 'y', 'w']
        self.chColors=cycle(self.colors)
        self.crosshairPlotItems = {}# pg.ScatterPlotItem()
#        self.vb.addItem(self.crosshairPlotItem)
        self.vb.scene().sigMouseMoved.connect(self.image_mouseMoved)

    def image_mouseMoved(self, pos):
        """
        Shows the mouse position of 2D Image on its crosshair label
        """
        pointer = self.vb.mapSceneToView(pos)
        x, y = pointer.x(), pointer.y()
        self.cursorXLabel.setText('Pix [X]: %d [%10.6f mm]' % (int(x/self.pixelSize),x*1e3))
        self.cursorYLabel.setText('Pix [y]: %d [%10.6f mm]' % (int(y/self.pixelSize),y*1e3))




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
        self.expTimeLineEdit.returnPressed.connect(self.exposureTimeChanged)
        self.acquirePeriodLineEdit.returnPressed.connect(self.acquirePeriodChanged)
        self.openImageFilePushButton.clicked.connect(self.openImageFile)

        self.imageUpdated.connect(self.updatePlots)
        self.startUpdatePushButton.clicked.connect(self.onStartUpdate)
        self.stopUpdatePushButton.clicked.connect(self.onStopUpdate)
        self.horROIWidthSpinBox.valueChanged.connect(self.onROIWinXChanged)
        self.verROIWidthSpinBox.valueChanged.connect(self.onROIWinYChanged)
        self.adReader.imageSizeXChanged.connect(self.onSizeXChanged)
        self.adReader.imageSizeYChanged.connect(self.onSizeYChanged)
        self.pixelSizeLineEdit.returnPressed.connect(self.onPixelSizeChanged)

        self.colorModeComboBox.currentIndexChanged.connect(self.colorModeChanged)

        self.saveImagePushButton.clicked.connect(self.saveImage)
        self.saveHorProfilesPushButton.clicked.connect(self.saveHorProfile)
        self.saveVerProfilesPushButton.clicked.connect(self.saveVerProfile)

        self.posTimeSeriesReady.connect(self.updatePosSeriesPlot)
        self.widTimeSeriesReady.connect(self.updateWidSeriesPlot)

        self.addCrosshairPushButton.clicked.connect(self.addCrosshairDlg)
        self.removeCrosshairPushButton.clicked.connect(self.removeCrosshair)
        self.openCrosshairPushButton.clicked.connect(self.openCrosshair)
        self.saveCrosshairPushButton.clicked.connect(self.saveCrosshair)

        self.hideHorizontalROICheckBox.stateChanged.connect(self.horizontalROI_viewChanged)
        self.hideVerticalROICheckBox.stateChanged.connect(self.verticalROI_viewChanged)

    def horizontalROI_viewChanged(self):
        if self.hideHorizontalROICheckBox.checkState()==Qt.Checked:
            self.horLine.hide()
        else:
            self.horLine.show()

    def verticalROI_viewChanged(self):
        if self.hideVerticalROICheckBox.checkState() == Qt.Checked:
            self.verLine.hide()
        else:
            self.verLine.show()

    def addCrosshairDlg(self):
        self.msgDlg=QtGui.QDialog(self)
        vlayout=QtGui.QVBoxLayout(self.msgDlg)
        self.msgDlg.label=QtGui.QLabel('Please click on the image to select a position for the crosshair')
        self.msgDlg.btn=QtGui.QPushButton('OK')
        self.msgDlg.btn.clicked.connect(self.addCrosshair)
        vlayout.addWidget(self.msgDlg.label)
        vlayout.addWidget(self.msgDlg.btn)
        self.msgDlg.setLayout(vlayout)
        self.msgDlg.setModal(False)
        self.msgDlg.show()

    def addCrosshair(self):
        self.crosshairTableWidget.blockSignals(True)
        rowNum = self.crosshairTableWidget.rowCount()
        colNum = self.crosshairTableWidget.columnCount()
        print('ch_%d'%rowNum, self.crosshairTableWidget.item(rowNum - 1, 0).text())
        if rowNum>0 and 'ch_%d'%rowNum==self.crosshairTableWidget.item(rowNum-1,0).text():
            name='ch_%d'%(rowNum+1)
        else:
            name='ch_%d'%rowNum
        self.crosshair.append({'Name':name,'Pos-X (mm)':self.crosshair_X*1e3,
                               'Pos-Y (mm)':self.crosshair_Y*1e3,
                               'Linewidth (pix)':1.0,
                               'Color':next(self.chColors),
                               'Show':True})
        self.crosshairTableWidget.setData(self.crosshair)
        self.colorButtons[rowNum] = pg.ColorButton(color=self.crosshair[rowNum]['Color'])
        self.colorButtons[rowNum].sigColorChanging.connect(self.cellDataChanged)
        self.crosshairTableWidget.item(rowNum, 5).setText('')
        self.crosshairTableWidget.item(rowNum, 5).setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        if self.crosshair[rowNum]['Show']:
            self.crosshairTableWidget.item(rowNum, 5).setCheckState(Qt.Checked)  # , self.showCheckBoxes[rowNum])
        else:
            self.crosshairTableWidget.item(rowNum, 5).setCheckState(Qt.Unchecked)  # , self.showCheckBoxes[rowNum])
        self.crosshairTableWidget.setCellWidget(rowNum, 4, self.colorButtons[rowNum])
        self.crosshairTableWidget.cellChanged.connect(self.cellDataChanged)
        for row in range(rowNum):
            self.colorButtons[row]=pg.ColorButton(color=self.crosshair[row]['Color'])
            self.colorButtons[row].sigColorChanging.connect(self.cellDataChanged)
            self.crosshairTableWidget.item(row, 5).setText('')
            self.crosshairTableWidget.item(row, 5).setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            if self.crosshair[row]['Show']:
                self.crosshairTableWidget.item(row, 5).setCheckState(Qt.Checked)
            else:
                self.crosshairTableWidget.item(row, 5).setCheckState(Qt.Unchecked)
            self.crosshairTableWidget.cellChanged.connect(self.cellDataChanged)
            self.crosshairTableWidget.setCellWidget(row, 4, self.colorButtons[row])
        self.updateCrosshairPlot()
        self.msgDlg.accept()
        self.crosshairTableWidget.blockSignals(False)
        self.removeCrosshairPushButton.setEnabled(True)

    def cellDataChanged(self):
        rowNum = self.crosshairTableWidget.rowCount()
        for row in range(rowNum):
            self.crosshair[row]['Pos-X (mm)'] = float(self.crosshairTableWidget.item(row, 1).text())
            self.crosshair[row]['Pos-Y (mm)'] = float(self.crosshairTableWidget.item(row, 2).text())
            self.crosshair[row]['Linewidth (pix)'] = float(self.crosshairTableWidget.item(row, 3).text())
            self.crosshair[row]['Color']=self.colorButtons[row].color()
            if self.crosshairTableWidget.item(row,5).checkState()==Qt.Checked:
                self.crosshair[row]['Show']=True
            else:
                self.crosshair[row]['Show']=False
        self.updateCrosshairPlot()

    def updateCrosshairPlot(self):
        for i, ch in enumerate(self.crosshair):
            if ch['Show']:
                # crosshair_list.append({'pos':(ch['Pos-X (mm)']*1e-3,ch['Pos-Y (mm)']*1e-3),
                #             'size':ch['Size (pix)'],
                #             'pen':None,
                #             'brush':ch['Color'],
                #             'symbol':'x'})
                try:
                    self.crosshairPlotItems[ch['Name']]['vertical'].setValue(ch['Pos-X (mm)']*1e-3)
                    self.crosshairPlotItems[ch['Name']]['vertical'].setPen(pg.mkPen(ch['Color'],width=ch['Linewidth ('
                                                                                                       'pix)']))
                    self.crosshairPlotItems[ch['Name']]['horizontal'].setValue(ch['Pos-Y (mm)']*1e-3)
                    self.crosshairPlotItems[ch['Name']]['horizontal'].setPen(pg.mkPen(ch['Color'], width=ch['Linewidth ('
                                                                                                 'pix)']))
                except:
                    self.crosshairPlotItems[ch['Name']]={
                        'vertical':pg.InfiniteLine(pos=ch['Pos-X (mm)']*1e-3, angle=90, pen=pg.mkPen(ch['Color'],
                                                                                                   width=ch[
                                                                                                       'Linewidth ('
                                                                                                       'pix)']),
                                                   movable=False, label=ch['Name']),
                        'horizontal': pg.InfiniteLine(pos=ch['Pos-Y (mm)'] * 1e-3, angle=0, pen=pg.mkPen(ch['Color'],
                                                                                                        width=ch[
                                                                                                            'Linewidth ('
                                                                                                            'pix)']),
                                                    movable=False, label=ch['Name'])
                    }
                    self.vb.addItem(self.crosshairPlotItems[ch['Name']]['vertical'])
                    self.vb.addItem(self.crosshairPlotItems[ch['Name']]['horizontal'])

                self.crosshairPlotItems[ch['Name']]['vertical'].show()
                self.crosshairPlotItems[ch['Name']]['horizontal'].show()
            else:
                self.crosshairPlotItems[ch['Name']]['vertical'].hide()
                self.crosshairPlotItems[ch['Name']]['horizontal'].hide()


    def removeCrosshair(self):
        self.crosshairTableWidget.blockSignals(True)
        indices=self.crosshairTableWidget.selectionModel().selectedRows()
        for index in sorted(indices, reverse=True):
            name=self.crosshairTableWidget.item(index.row(),0).text()
            self.vb.removeItem(self.crosshairPlotItems[name]['vertical'])
            self.vb.removeItem(self.crosshairPlotItems[name]['horizontal'])
            self.crosshair.pop(index.row())
            del self.crosshairPlotItems[name]
        self.crosshairTableWidget.setData(self.crosshair)
        rowNum = self.crosshairTableWidget.rowCount()
        for row in range(rowNum):
            self.colorButtons[row] = pg.ColorButton(color=self.crosshair[row]['Color'])
            self.colorButtons[row].sigColorChanging.connect(self.cellDataChanged)
            self.crosshairTableWidget.item(row, 5).setText('')
            self.crosshairTableWidget.item(row, 5).setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            if self.crosshair[row]['Show']:
                self.crosshairTableWidget.item(row, 5).setCheckState(Qt.Checked)
            else:
                self.crosshairTableWidget.item(row, 5).setCheckState(Qt.Unchecked)
            self.crosshairTableWidget.cellChanged.connect(self.cellDataChanged)
            self.crosshairTableWidget.setCellWidget(row, 4, self.colorButtons[row])
        self.crosshairTableWidget.blockSignals(False)
        if self.crosshairTableWidget.rowCount()==0:
            self.removeCrosshairPushButton.setEnabled(False)

    def removeAllCrosshair(self):
        self.crosshairTableWidget.blockSignals(True)
        for row in range(self.crosshairTableWidget.rowCount()-1,-1,-1):
            name = self.crosshairTableWidget.item(row, 0).text()
            self.vb.removeItem(self.crosshairPlotItems[name]['vertical'])
            self.vb.removeItem(self.crosshairPlotItems[name]['horizontal'])
            self.crosshair.pop(row)
            del self.crosshairPlotItems[name]
        self.crosshairTableWidget.setData(self.crosshair)
        self.crosshairTableWidget.blockSignals(False)
        self.removeCrosshairPushButton.setEnabled(False)


    def openCrosshair(self):
        fname=QtGui.QFileDialog.getOpenFileName(self,'Open Crosshair File','','Crosshair Files (*.chr)')[0]
        if fname!='':
            fh=open(fname,'r')
            self.removeAllCrosshair()
            lines=fh.readlines()
            keys=lines[1].strip()[1:].split('\t')
            self.crosshair = []
            for line in lines:
                if line[0]!='#':
                    values=line.strip().split('\t')
                    ch={}
                    for i,value in enumerate(values):
                        try:
                            ch[keys[i]]=float(value)
                        except:
                            ch[keys[i]]=value
                    self.crosshair.append(ch)
            self.crosshairTableWidget.blockSignals(True)
            self.crosshairTableWidget.setData(self.crosshair)
            rowNum=self.crosshairTableWidget.rowCount()
            for row in range(rowNum):
                self.colorButtons[row] = pg.ColorButton(color=self.crosshair[row]['Color'])
                self.colorButtons[row].sigColorChanging.connect(self.cellDataChanged)
                self.crosshairTableWidget.item(row, 5).setText('')
                self.crosshairTableWidget.item(row, 5).setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                if self.crosshair[row]['Show']:
                    self.crosshairTableWidget.item(row, 5).setCheckState(Qt.Checked)
                else:
                    self.crosshairTableWidget.item(row, 5).setCheckState(Qt.Unchecked)
                self.crosshairTableWidget.cellChanged.connect(self.cellDataChanged)
                self.crosshairTableWidget.setCellWidget(row, 4, self.colorButtons[row])
            self.crosshairTableWidget.blockSignals(False)
            self.crosshairPlotItems={}
            self.updateCrosshairPlot()
            self.removeCrosshairPushButton.setEnabled(True)


    def saveCrosshair(self):
        if self.crosshairTableWidget.rowCount()>0:
            fname=QtGui.QFileDialog.getSaveFileName(self,'Save file as','', 'Crosshair Files (*.chr)')[0]
            if fname!='':
                if os.path.splitext(fname)[1]=='':
                    fname=fname+'.chr'
                line='# Crosshair file saved on %s\n'%time.ctime()
                line+='#'
                for key in self.crosshair[0]:
                    line+='%s\t'%key
                line+='\n'
                for ch in self.crosshair:
                    for key in ch.keys():
                        line+=str(ch[key])+'\t'
                    line+='\n'
                fh=open(fname,'w')
                fh.writelines(line)
                fh.close()




    def exposureTimeChanged(self):
        if self.startUpdate:
            QtGui.QMessageBox.warning(self,"Warning","Please Stop the updating of the image first",QtGui.QMessageBox.Ok)
            self.expTimeLineEdit.setText(str(self.expTime))
            return
        else:
            self.expTime=float(self.expTimeLineEdit.text())
            epics.caput(self.detPV + 'cam1:AcquireTime', self.expTime)

    def acquirePeriodChanged(self):
        if self.startUpdate:
            QtGui.QMessageBox.warning(self,"Warning","Please Stop the updating of the image first",QtGui.QMessageBox.Ok)
            self.acquirePeriodLineEdit.setText(str(self.period))
            return
        else:
            self.period=float(self.acquirePeriodLineEdit.text())
            epics.caput(self.detPV+'cam1:AcquirePeriod',self.period)

    def colorModeChanged(self):
        if self.startUpdate:
            QtGui.QMessageBox.warning(self,"Warning","Please Stop the updating of the image first",QtGui.QMessageBox.Ok)
            self.colorModeComboBox.setCurrentText(self.colorMode)
            return
        else:
            self.colorMode=self.colorModeComboBox.currentText()
            if self.colorMode=='Greyscale':
                epics.caput(self.detPV+'cam1:ColorMode', 0)
                epics.caput(self.detPV+'cam1:BayerConvert', 0)
            else:
                epics.caput(self.detPV+'cam1:ColorMode', 2)
                epics.caput(self.detPV + 'cam1:BayerConvert', 1)
            epics.caput(BYTES2STR(self.detPV + "cam1:ArrayCounter"), 0)
            epics.caput(BYTES2STR(self.detPV + "cam1:Acquire"), 1)
            time.sleep(0.2)
            epics.caput(BYTES2STR(self.detPV + "cam1:Acquire"), 0)
            epics.caput(BYTES2STR(self.detPV + "cam1:ArrayCounter"), 0)

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
        if self.startUpdate:
            QtGui.QMessageBox.warning(self,"Warning","Please Stop the updating of the image first",QtGui.QMessageBox.Ok)
            return
        else:
            self.pixelSize=float(self.pixelSizeLineEdit.text())*1e-6
            try:
                self.create_PlotLayout(image=None)
            except:
                pass

    def onSizeXChanged(self,value):
        self.imageSizeXLineEdit.setText('%d'%value)

    def onSizeYChanged(self,value):
        self.imageSizeYLineEdit.setText('%d'%value)

    def onROIWinXChanged(self):
        self.ROIWinX=self.horROIWidthSpinBox.value()
        left,right=self.verLine.getRegion()
        x=(right + left)*self.pixelSize/self.oldPixelSize / 2
        self.verLine.setRegion((x - self.ROIWinX * self.pixelSize / 2,x + self.ROIWinX * self.pixelSize / 2))


    def onROIWinYChanged(self):
        self.ROIWinY=self.verROIWidthSpinBox.value()
        up,down=self.horLine.getRegion()
        y = (up + down)*self.pixelSize/self.oldPixelSize / 2
        self.horLine.setRegion((y - self.ROIWinY * self.pixelSize / 2, y + self.ROIWinY * self.pixelSize / 2))

    def onStartUpdate(self):
        self.cutSeriesExists=False
        self.widSeriesExists=False
        epics.caput(BYTES2STR(self.detPV + "cam1:ArrayCounter"), 0)
        epics.caput(BYTES2STR(self.detPV + "cam1:Acquire"), 1)
        epics.camonitor(BYTES2STR(self.detPV + "image1:ArrayCounter_RBV"),callback=self.onArrayDataUpdate)
        self.arrayDataUpdated.connect(self.start_stop_Update)
        self.startUpdate=True
        self.startTime = time.time()
        self.posTimeData = []
        self.widTimeData = []
        self.startUpdatePushButton.setEnabled(False)
        self.stopUpdatePushButton.setEnabled(True)
        self.setOutputOptions(enabled=False)
        self.detPVLineEdit.setEnabled(False)

    def onArrayDataUpdate(self,**kwargs):
        self.arrayDataUpdated.emit()


    def onStopUpdate(self):
        self.startUpdate=False
        self.arrayDataUpdated.disconnect(self.start_stop_Update)
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
        data=self.adReader.data_PV.get()
        if self.colorMode == 'Greyscale':
            self.imgData = np.rot90(data.reshape(self.adReader.sizeY, self.adReader.sizeX), k=-1,
                                    axes=(0, 1))
            self.greyData = self.imgData
        else:
            self.imgData = np.rot90(data.reshape(self.adReader.sizeY, self.adReader.sizeX, 3), k=-1, axes=(0, 1))
            self.greyData = self.imgData[..., :3]#@np.array([0.299, 0.587, 0.114])
        self.imgPlot.setImage(self.imgData,autoLevels=False)
        self.imageUpdated.emit(self.imgData)


    def create_PlotLayout(self,image=None):
        self.xValues=self.pixelSize*np.arange(self.adReader.sizeX)
        self.yValues=self.pixelSize*np.arange(self.adReader.sizeY)
        #self.vb = self.imageLayout.addViewBox(lockAspect=True)
        self.imagePlot=self.imageLayout.getItem(0,0)
        if self.imagePlot is None:
            self.imagePlot = self.imageLayout.addPlot(title='2D Image')
            self.imagePlot.setLabel('left',text='Y',units='m')
            self.imagePlot.setLabel('bottom',text='X',units='m')
            self.imagePlot.setAspectLocked(lock=False,ratio=1)

        try:
            self.imagePlot.removeItem(self.imgPlot)
        except:
            pass
        self.imgPlot = pg.ImageItem()
        self.imgPlot.scale(self.pixelSize, self.pixelSize)
        self.oldPixelSize=copy.copy(self.pixelSize)
        self.imagePlot.addItem(self.imgPlot)
        self.vb = self.imagePlot.getViewBox()
        self.vb.scene().sigMouseClicked.connect(self.onClick)
        self.vb.addItem(self.imgPlot)
        self.vb.setRange(QtCore.QRectF(0, 0, self.adReader.sizeX, self.adReader.sizeY))
        if image is None:
            try:
                data = self.adReader.data_PV.get()
                if self.colorMode=='Greyscale':
                    self.imgData = np.rot90(data.reshape(self.adReader.sizeY, self.adReader.sizeX), k=-1,
                                            axes=(0, 1))
                    self.greyData=self.imgData
                else:
                    self.imgData = np.rot90(data.reshape(self.adReader.sizeY, self.adReader.sizeX,3), k=-1, axes=(0, 1))
                    self.greyData = np.dot(self.imgData[..., :3], [0.299, 0.587, 0.114])
            except:
                data=imread('2dimage_2.tif')
                self.imgData = np.rot90(data.reshape(self.adReader.sizeY, self.adReader.sizeX), k=-1, axes=(0, 1))
                self.greyData = self.imgData
        else:
            data=imread(image)
            self.imgData = np.rot90(data.reshape(self.adReader.sizeY, self.adReader.sizeX), k=-1, axes=(0, 1))
        self.imgPlot.setImage(self.imgData,autoLevels=True)
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
            if evt.double():
                self.verLine.setRegion(((x - self.ROIWinX / 2) * self.pixelSize, (x + self.ROIWinX / 2) * self.pixelSize))
                self.horLine.setRegion(((y - self.ROIWinY / 2) * self.pixelSize, (y + self.ROIWinY / 2) * self.pixelSize))
        self.crosshair_X=pos.x()
        self.crosshair_Y=pos.y()
        try:
            self.msgDlg.label.setText('Crosshair position selected. Please OK to draw the crosshair.')
        except:
            pass

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
        self.verCutData=np.sum(self.greyData[self.left:self.right,:],axis=0)
        try:
            self.verCutPlot.setData(self.verCutData,self.yValues)
        except:
            self.verCutPlot=self.verCut.plot(self.verCutData,self.yValues, pen=pg.mkPen('y'))
        minm=np.min(self.verCutData)
        maxm=np.max(self.verCutData)
        pos=np.where(self.verCutData>(maxm+minm)/2)
        verCut = self.verCutData[pos]
        self.cutPeakY = np.sum(verCut * self.yValues[pos]) / np.sum(verCut)
        cutY = np.argwhere(verCut >= np.max(verCut) / 2.0)
        self.cutWidthY = np.abs(self.yValues[cutY[0]] - self.yValues[cutY[-1]])
        self.verCut.setTitle("Peak=%.4f, Wid=%.4f" % (1e3 * self.cutPeakY, 1e3 * self.cutWidthY))
        #self.verCut.setXRange(0,np.max(verCut))

    def updateHorCut(self):
        self.horCutData=np.sum(self.greyData[:,self.up:self.down],axis=1)
        try:
            self.horCutPlot.setData(self.xValues,self.horCutData)
        except:
            self.horCutPlot=self.horCut.plot(self.xValues,self.horCutData, pen=pg.mkPen('b'))
        minm=np.min(self.horCutData)
        maxm=np.max(self.horCutData)
        pos=np.where(self.horCutData>(maxm+minm)/2)
        horCut = self.horCutData[pos]
        self.cutPeakX = np.sum(horCut * self.xValues[pos]) / np.sum(horCut)
        cutX = np.argwhere(horCut >= np.max(horCut) / 2.0)
        self.cutWidthX = np.abs(self.xValues[cutX[0]] - self.xValues[cutX[-1]])
        self.horCut.setTitle("Peak=%.4f, Wid=%.4f" % (1e3 * self.cutPeakX, 1e3 * self.cutWidthX))

    def getSaveTimeSeriesFile(self):
        self.saveFile = QtGui.QFileDialog.getSaveFileName(self, "Please provide the file for saving the time-"
                                                                "series for the horizontal peak profiles ")[0]
        if self.saveFile!='':
            self.fh = open(self.saveFile, 'w')
            self.saveStartTime = time.time()
            self.fh.write('#File saved on %s'%time.asctime())
            self.fh.write('#Exposure_time=%.4f\n'%self.expTime)
            self.fh.write('#col_names=[\'time\',\'m1\',\'m2\',\'m3\',\'m4\',\'m5\',\'m6\',\'monB\',\'horPeakPos(mm)\','
                          '\'horPeakWid(mm)\','
                          '\'verPeakPos('
                          'mm)\','
                          '\'verPeakWid(mm)\']\n')
            #self.fh.write('#File created on ' + self.time.asctime() + '\n')
            self.fh.write('#time m1 m2 m3 m4 m5 m6 monB horPeakPos(mm) horPeakWid(mm) verPeakPos(mm) verPeakWid(mm) '
                          '\n')
        else:
            self.saveFile=None
            self.autoSaveCheckBox.setCheckState(0)

    def getMonoValues(self):
        self.m1=epics.caget(BYTES2STR("15IDA:m1.REP"))
        self.m2=epics.caget(BYTES2STR("15IDA:m2.REP"))
        self.m3=epics.caget(BYTES2STR("15IDA:m3.REP"))
        self.m4=epics.caget(BYTES2STR("15IDA:m4.REP"))
        self.m5=epics.caget(BYTES2STR("15IDA:m5.REP"))
        self.m6=epics.caget(BYTES2STR("15IDA:m6.REP"))
        self.monB=epics.caget(BYTES2STR("15IDB:scaler1.S2"))

    def updatePlots(self):
#        self.updateSums()
        self.updateVerCut()
        self.updateHorCut()
        if self.autoSaveCheckBox.isChecked():
            if self.saveFile is not None:
                t=time.time()
                self.getMonoValues()
                self.fh.write('%.6f %.d %d %d %d %d %d %d %.6f %.6f %.6f %.6f\n'%(t-self.saveStartTime,
                                                                                             self.m1,self.m2,self.m3,
                                                                                             self.m4,self.m5,self.m6,
                                                                                             self.monB,
                                                                                             1e3*self.cutPeakX,
                                                                                             1e3*self.cutWidthX,
                                                                                             1e3*self.cutPeakY,
                                                                                             1e3*self.cutWidthY))
            else:
                self.imageUpdated.disconnect(self.updatePlots)
                self.getSaveTimeSeriesFile()
                self.imageUpdated.connect(self.updatePlots)
        else:
            try:
                self.saveFile=None
                self.fh.close()
            except:
                pass

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
