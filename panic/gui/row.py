import panic, sys, re, os, traceback, time
import PyTango, fandango, taurus, taurus.qt.qtgui.base
from fandango.functional import *
from fandango import Catched
from widgets import QtCore, QtGui, Qt, TRACE_LEVEL
from taurus.core import TaurusEventType
from taurus.qt.qtgui.base import TaurusBaseComponent
from editor import AlarmForm
from widgets import getAlarmTimestamp,trace,clean_str,\
  getThemeIcon,getAttrValue, SNAP_ALLOWED, WindowManager
#from htmlview import *

REFRESH_TIME = 10000
DEVICE_TIMEOUT = 250

class QAlarm(panic.Alarm):
  
    def set_model_obj(self,alarm):
        #self.setup(obj2dict(alarm))
        self._alarm = alarm
    
    def get_disabled(self,force=False):
        val = None
        try:
            if not force and self.use_list: 
                if not getattr(self,'dis_attr',None):
                    self.dis_attr = taurus.Attribute(self.device+'/DisabledAlarms')
                    self.dis_attr.changePollingPeriod(REFRESH_TIME)
                dis_val = getAttrValue(self.dis_attr.read())
                val = any(re.split('[: ,;]',a)[0]==self.alarm.tag for a in (dis_val or []))
            else: 
                val = taurus.Device(self.alarm.device).command_inout('CheckDisabled',self.alarm.tag)
                if force: self.alarmDisabled = val
        except:
            print fandango.log.except2str()
        #print 'In AlarmRow(%s).get_disabled(): %s'%(self.alarm.tag,val)
        return val
        
    def get_alarm_time(self, alarm=None, attr_value=None, null = float('nan')):
        alarm = alarm or self.alarm
        try:
            if not self.alarm.active:
                self.alarm.active = getAlarmTimestamp(alarm)
            #print 'AlarmRow(%s).get_alarm_date(%s)'%(alarm.tag,alarm.active)
            return self.alarm.active if self.alarm.active else 0
        except:
            print traceback.format_exc()
        return fandango.END_OF_TIME if self.alarm.active else 0
        
    def get_alarm_date(self, alarm=None, attr_value=None, null = ' NaN '):
        try:
            return ('%'+str(self.DATE_SIZE)+'s')%fandango.time2str(self.get_alarm_time(alarm,attr_value))
        except:
            print traceback.format_exc()
            return str(null)
          
    def eventReceived(self,evt_src,evt_type,evt_value):
        try:
            debug = 'debug' in str(evt_src).lower() or TRACE_LEVEL>0
            now = fandango.time2str()
            evtype = str(TaurusEventType.reverseLookup[evt_type])
            # Direct getattr(o,n,v) fails on some taurus classes
            is_empty = (hasattr(evt_value,'is_empty') and getattr(evt_value,'is_empty')) or False
            evvalue = getAttrValue(evt_value) if not is_empty else []
            
            if debug: 
                print '\n'
                trace('%s: In AlarmRow(%s).eventReceived(%s,%s,%s)'%(fandango.time2str(),self.alarm.tag,evt_src,evtype,evvalue),clean=True)
            disabled,acknowledged,quality,value = self.alarmDisabled,self.alarmAcknowledged,self.quality,bool(evvalue) #bool(self.alarm.active)
            if self.qtparent and getattr(self.qtparent,'api',None): self.alarm = self.qtparent.api[self.tag] #Using common api object
            
            #Ignoring Config Events
            if evt_type==TaurusEventType.Config:
                if debug: trace('%s: AlarmRow(%s).eventReceived(CONFIG): %s' % (now,self.alarm.tag,str(evt_value)[:20]),clean=True)
                return

            #Filtering Error Events
            elif evt_type==TaurusEventType.Error or evvalue is None:
                error = True
                self.errors+=1
                if self.errors>=self.MAX_ERRORS: 
                    #After MAX_ERRORS the alarm is simply ignored
                    self.alarm.active,self.quality = None,PyTango.AttrQuality.ATTR_INVALID
                if not self.errors%self.MAX_ERRORS:
                    if 'EventConsumer' not in str(evt_value): 
                        trace('%s: AlarmRow(%s).eventReceived(ERROR): %s' %(now,self.alarm.tag,'ERRORS=%s!:\n\t%s'%(self.errors,fandango.except2str(evt_value,80))),clean=True)
                    #if self.value is None: taurus.Attribute(self.model).changePollingPeriod(5*REFRESH_TIME)
                    if not self.changed and self.errors==self.MAX_ERRORS or 'Exception' not in self.status: 
                        print '%s : %s.emitValueChanged(ERROR!)'%(now,self.alarm.tag)
                        print 'ERROR: %s(%s)' % (type(evt_value),clean_str(evt_value))
                        self.qtparent.emitValueChanged()
                        self.changed = True #This flag is set here, and set to False after updating row style
                        self.updateStyle(event=True,error=fandango.except2str(evt_value)) #It seems necessary to update the row text, color and icon
                else: 
                    if debug: trace('In AlarmRow(%s).eventReceived(%s,%s,%d/%d)' % (self.alarm.tag,evt_src,evtype,self.errors,self.MAX_ERRORS),clean=True)
                    pass

            #Change Events
            elif evt_type==TaurusEventType.Change or evt_type==TaurusEventType.Periodic:
                self.errors = 0
                
                # Refresh period not changed as these lines slows down a lot!!
                #ta = taurus.Attribute(self.model)
                #if self.value is None: ta.changePollingPeriod(5*REFRESH_TIME)
                #elif ta.getPollingPeriod()!=REFRESH_TIME: ta.changePollingPeriod(REFRESH_TIME)
                
                disabled = self.get_disabled()
                acknowledged = self.get_acknowledged()
                if str(self.model).endswith('/ActiveAlarms'):
                    value,quality = any(s.startswith(self.alarm.tag+':') for s in (evvalue or [])),self.alarm.get_quality()
                else:
                    value,quality = evvalue,evt_value.quality
                
                if debug: trace('In AlarmRow(%s).eventReceived(%s,%s,%s)' % (self.alarm.tag,evt_src,str(TaurusEventType.reverseLookup[evt_type]),evvalue),clean=True)
                if debug: trace('\t%s (%s), dis:%s, ack:%s'%(value,quality,disabled,acknowledged))
                
                if  value!=bool(self.alarm.active) or quality!=self.quality or disabled!=self.alarmDisabled or acknowledged!=self.alarmAcknowledged:
                    if not self.changed: 
                        #print '%s : %s.emitValueChanged(%s)'%(fandango.time2str(),self.alarm.tag,value)
                        self.qtparent.emitValueChanged()
                    self.changed = True #This flag is set here, and set to False after updating row style
                
                self.alarmDisabled = disabled
                self.alarmAcknowledged = acknowledged
                self.quality = quality
                self.alarm.active = getAlarmTimestamp(self.alarm) if value else 0 #It will get the date from ActiveAlarms array
                
                if debug: trace('\tactive since %s'%time2str(self.alarm.active))
                
                self.updateStyle(event=True,error=False)
            else: 
                print '\tUnknown event type?!? %s' % evt_type
        except:
            try: print 'Exception in eventReceived(%s,...): \n%s' %(evt_src,fandango.log.except2str())
            except : print 'eventReceived(...)!'*80+'\n'+traceback.format_exc()
        if debug: print '\n'
            
    def updateIfChanged(self):
        if self.changed:
            print 'AlarmRow(%s).updateIfChanged(changed=True)'%(self.alarm.tag)
            self.updateStyle(event=True,error=self.errors>self.MAX_ERRORS)
            self.changed = False

    def updateStyle(self,event=False,error=False):
        #trace('%s -> AlarmRow(%s).updateStyle(event=%s)'%(time.ctime(),self.alarm.tag,event),clean=True)
        if getattr(self.qtparent,'_attributesSignalsBlocked',False):
            #print '\tupdateStyle(): blocked!'
            return
        if event:
            try:
                self.font=QtGui.QFont(QtCore.QString("Courier"))
                self.font.setPointSize(10)
                if error:
                    if self.errors>=self.MAX_ERRORS and not self.errors%self.MAX_ERRORS:
                        self.was_ok = self.alarm.active or self.alarm.recovered
                        self.alarm.active,self.alarm.recovered,self.alarm.counter = 0,0,0
                        self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,None,False,QtGui.QColor("grey").light(),QtGui.QColor("white"))
                        if self.was_ok:
                            self.font.setBold(False)
                        error_text = clean_str(error if isinstance(error,basestring) else 'disabled').split('=',1)[-1].strip()[:40]
                        self.setText('   '+' - '.join((self.get_tag_text(),error_text)))
                        self.status = 'Exception received, check device %s'%self.alarm.device
                elif self.alarm.active is None:
                    #trace('updateStyle(%s): value not received yet' %(self.alarm.tag),clean=True)
                    pass
                else:
                    trace('AlarmRow.updateStyle: %s = %s (%s)' %(self.alarm.tag,self.alarm.active,self.quality),clean=True)
                    if self.alarm.active and not self.alarmDisabled:
                        if self.quality==PyTango.AttrQuality.ATTR_ALARM:
                            trace('alarm')
                            if self.alarmAcknowledged:
                                self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"media-playback-pause",False,QtGui.QColor("black"),QtGui.QColor("red").lighter())
                            else:
                                self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"software-update-urgent",False,QtGui.QColor("black"),QtGui.QColor("red").lighter())
                        elif self.quality==PyTango.AttrQuality.ATTR_WARNING:
                            trace('warning')
                            if self.alarmAcknowledged:
                                self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"media-playback-pause",False,QtGui.QColor("black"),QtGui.QColor("orange").lighter())
                            else:
                                self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"emblem-important",False,QtGui.QColor("black"),QtGui.QColor("orange").lighter())
                        elif self.quality==PyTango.AttrQuality.ATTR_VALID:
                            trace('debug')
                            if self.alarmAcknowledged:
                                self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"media-playback-pause",False,QtGui.QColor("black"),QtGui.QColor("yellow").lighter())
                            else:
                                self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"applications-development",False,QtGui.QColor("black"),QtGui.QColor("yellow").lighter())
                        else: 
                            print '\tUnknown event quality?!? %s' % self.quality
                            
                        if self.alarm.counter<2:
                            self.font.setBold(True)
                        self.alarm.recovered,self.alarm.counter = 0,2

                        #else: self.font.SetBold(False) #Good to keep it, to see what changed
                        self.status = 'Alarm Acknowledged, no more messages will be sent' if self.alarmAcknowledged else 'Alarm is ACTIVE'
                        self.setText(' | '.join((self.get_tag_text(),self.get_alarm_date(), self.alarm.description)))
                        #self.setText('%45s | %30s'%(str(self.alarm.tag)[:45], self.get_alarm_date(), self.alarm.description))

                    elif self.alarm.active in (False,0) and not self.alarmDisabled:
                        if self.alarmAcknowledged:
                            self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"media-playback-pause",False,QtGui.QColor("green").lighter(),QtGui.QColor("white"))
                        else:
                            self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"emblem-system",False,QtGui.QColor("green").lighter(),QtGui.QColor("white"))
                        if not self.alarm.recovered:
                            #trace('\teventReceived(%s): %s => %s' %(self.alarm.tag,self.alarm.active,self.value),clean=True)
                            if self.alarm.counter>1: 
                                self.font.setBold(True)
                            self.alarm.active,self.alarm.recovered,self.alarm.counter = 0,time.time(),1
                        #else: self.font.SetBold(False) #Good to keep it, to see what changed
                        self.status = 'Alarm has NOT been triggered'
                        self.setText(' - '.join((self.get_tag_text(),'Not triggered')))

                    else: #AlarmDisabled or value = None
                        self.status = 'Alarm is Disabled, status will not be updated'
                        self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"dialog-error",False,QtGui.QColor("black"),QtGui.QColor("grey").lighter())
                        
                    #if self.qtparent.USE_EVENT_REFRESH: 
                self.setToolTip('\n'.join([
                    self.status,'',
                    'Severity: '+self.alarm.severity,
                    'Formula: '+self.alarm.formula,
                    'Description: %s'%self.alarm.description,
                    'Alarm Device: %s'%self.alarm.device,
                    'Archived: %s'%('Yes' if 'SNAP' in self.alarm.receivers else 'No'),
                    ]))
                self.setFont(self.font)
            except:
                print 'Exception in updateStyle(%s,...): \n%s' %(self.alarm.tag,traceback.format_exc())
        else:
            for klass in type(self).__bases__:
                try: 
                    if hasattr(klass,'updateStyle'): klass.updateStyle(self)
                except: pass

        pass
            
    @classmethod
    def setFontsAndColors(klass,tag,icon,bold,color,background):
        #print 'setFontsAndColors(%s,%s,%s,%s,%s)'%(tag,icon,bold,color.name(),background.name())
        tag = str(tag).lower()
        if tag in klass.ALL_ROWS:
            self = klass.ALL_ROWS[tag]
            self.alarmIcon=getThemeIcon(icon) if icon else None
            self.setIcon(self.alarmIcon or Qt.QIcon())
            self.font.setBold(bold)
            self.setTextColor(color)
            self.setBackgroundColor(background)
        else:
            print 'Tag %s is not in the list of AlarmRows: %s' % (tag,klass.ALL_ROWS.keys())
        
    
        
class QAlarmManager(QAlarm):
  
    @Catched
    def onContextMenu(self, point):
        self.popMenu = QtGui.QMenu(self)
        view = getattr(self,'view')
        items = self.getSelectedRows(extend=False)
        print('In onContextMenu(%s)'%items)
        row = self._ui.listWidget.currentItem()
        #self.popMenu.addAction(getThemeIcon("face-glasses"), "Preview Attr. Values",self.onSelectAll)

        act = self.popMenu.addAction(getThemeIcon("face-glasses"),
                                     "See Alarm Details",self.onView) 
        act.setEnabled(len(items)==1)
        act = self.popMenu.addAction(getThemeIcon("accessories-calculator"),
                                     "Preview Formula/Values",
            lambda s=self:WindowManager.addWindow(s.showAlarmPreview()))
        act.setEnabled(len(items)==1)
        self.popMenu.addAction(getThemeIcon("view-refresh"), 
                               "Sort/Update List",self.onSevFilter)

        act = self.popMenu.addAction(getThemeIcon("office-calendar"), 
                                     "View History",self.viewHistory)
        act.setEnabled(SNAP_ALLOWED and len(items)==1) 
            # and row.get_alarm_tag() in self.ctx_names)
            
        sevMenu = self.popMenu.addMenu('Change Severity')
        for S in ('ERROR','ALARM','WARNING','DEBUG'):
            action = sevMenu.addAction(S)
            self.connect(action, QtCore.SIGNAL("triggered()"), 
                lambda ks=items,s=S: 
                  self.setSeverity([k.get_alarm_tag() for k in ks],s))
        
        # Reset / Acknowledge options
        act = self.popMenu.addAction(getThemeIcon("edit-undo"), 
                                     "Reset Alarm(s)",self.ResetAlarm)

        items = [view.get_alarm_from_text(i.text()) for i in items]
        print('oncontextMenu(%s)'%items)
        items = [self.api[a] for a in items]
        act.setEnabled(any(i.active for i in items))

        if len([i.acknowledged for i in items]) in (len(items),0):
            self.popMenu.addAction(getThemeIcon("media-playback-pause"), "Acknowledge/Renounce Alarm(s)",self.onAckStateChanged)
            #(lambda checked=not row.alarmAcknowledged:self.onAckStateChanged(checked)))
        if len([i.disabled for i in items]) in (len(items),0):
            self.popMenu.addAction(getThemeIcon("dialog-error"), "Disable/Enable Alarm(s)",self.onDisStateChanged)
            
        # Edit options
        if self.expert:
            self.popMenu.addSeparator()
            act = self.popMenu.addAction(getThemeIcon("accessories-text-editor"), "Edit Alarm",self.onEdit)
            act.setEnabled(len(items)==1)
            act = self.popMenu.addAction(getThemeIcon("edit-copy"), "Clone Alarm",self.onClone)
            act.setEnabled(len(items)==1)
            act = self.popMenu.addAction(getThemeIcon("edit-clear"), "Delete Alarm",self.onDelete)
            act.setEnabled(len(items)==1)
            self.popMenu.addAction(getThemeIcon("applications-system"), "Advanced Config",self.onConfig)
            self.popMenu.addSeparator()
            act = self.popMenu.addAction(getThemeIcon("accessories-text-editor"), "TestDevice",lambda d=row.alarm.device:os.system('tg_devtest %s &'%d))
            act.setEnabled(len(items)==1)
        #self.popMenu.addSeparator()
        #self.popMenu.addAction(getThemeIcon("process-stop"), "close App",self.close)
        self.popMenu.exec_(self._ui.listWidget.mapToGlobal(point))

    def onEdit(self,edit=True):
        alarm = self.getCurrentAlarm()
        print "AlarmGUI.onEdit(%s)"%alarm
        forms = [f for f in WindowManager.WINDOWS if isinstance(f,AlarmForm) and f.getCurrentAlarm().tag==alarm.tag] 
        if forms: 
            form = forms[0]
            form.enableEditForm(edit)
            form.hide()
            form.show()
        else:
            form = WindowManager.addWindow(AlarmForm(self.parent()))
            form.connect(form,Qt.SIGNAL('valueChanged'),self.hurry)
            if edit: form.onEdit(alarm)
            else: form.setAlarmData(alarm)
        form.show()
        return form
        
    def onView(self):
        return self.onEdit(edit=False)
        
    def onNew(self):
        try:
            trace('onNew()')
            if not self.api.devices:
                v = Qt.QMessageBox.warning(self,'Warning','You should create a PyAlarm device first (using jive or config panel)!',Qt.QMessageBox.Ok)
                return
            if self._ui.listWidget.currentItem():
                self._ui.listWidget.currentItem().setSelected(False)
            form = AlarmForm(self.parent())
            trace('form')
            form.connect(form,Qt.SIGNAL('valueChanged'),self.hurry)
            form.onNew()
            form.show()
            return form
        except:
            traceback.print_exc()
        
    def onConfig(self):
        self.dac = dacWidget(device=self.getCurrentAlarm().device)
        self.dac.show()
        
    def onClone(self):
        alarm = self.getCurrentAlarm().tag
        trace("onClone(%s)"%alarm)
        new_tag,ok = Qt.QInputDialog.getText(self,'Input dialog','Please provide tag name for cloned alarm.',Qt.QLineEdit.Normal,alarm)
        if (ok and len(str(new_tag)) > 3):
            try:
                obj = self.api[alarm]
                self.api.add(str(new_tag), obj.device, formula=obj.formula, description=obj.description, receivers=obj.receivers, severity=obj.severity)
                self.onReload()
            except Exception,e:
                Qt.QMessageBox.critical(self,"Error!",str(e), QtGui.QMessageBox.AcceptRole, QtGui.QMessageBox.AcceptRole)
                trace(traceback.format_exc())

    def onDelete(self,tag=None,ask=True):
        tags = tag and [tag] or [getattr(r,'tag',r) for r in self.getSelectedRows(extend=False)]
        if ask:
            v = QtGui.QMessageBox.warning(None,'Pending Changes', \
                'The following alarms will be deleted:\n\t'+'\n\t'.join(tags), \
                QtGui.QMessageBox.Ok|QtGui.QMessageBox.Cancel)
            if v == QtGui.QMessageBox.Cancel: 
                return

            self.setAllowedUsers(self.api.get_admins_for_alarm(len(tags)==1 and tags[0]))
            if not self.validate('onDelete(%s)'%([a for a in tags])):
                return
        if len(tags)>1:
            [self.onDelete(tag,ask=False) for tag in tags]
        else:
            tag = tags[0]
            trace('onDelete(%s)'%tag)
            self.removeAlarmRow(tag)
            self.api.remove(tag)
            self.onReload()
            try:
                [f.close() for f in WindowManager.WINDOWS if isinstance(f,AlarmForm) and f.getCurrentAlarm().tag==tag] 
            except: pass

    ###############################################################################

    def viewHistory(self):
        alarm = str(self._ui.listWidget.currentItem().get_alarm_tag())

        if SNAP_ALLOWED and not self.snapi: 
          self.snapi = get_snap_api()

        if self.snapi:
          self.ctx_names=[c.name for c in self.snapi.get_contexts().values()]

        if alarm in self.ctx_names: 
          self.ahApp = ahWidget()
          self.ahApp.show()
          #self.ahApp.setAlarmCombo(alarm=str(self._ui.listWidget.currentItem().text().split('|')[0]).strip(' '))
          self.ahApp.setAlarmCombo(alarm=alarm)
        else:
          v = QtGui.QMessageBox.warning(None,'Not Archived', \
              'This alarm has not recorded history',QtGui.QMessageBox.Ok)
          return
        
        
    def showAlarmPreview(self):
        form = AlarmPreview(tag=self.getCurrentAlarm(),parent=self.parent())
        form.show()
        return form
                
    def ResetAlarm(self,alarm=None):
        prompt,cmt=QtGui.QInputDialog,''
        if alarm is None:
            alarms = [t.alarm or api[t.tag] for t in self.getSelectedRows(extend=True) if not t.alarm or t.alarm.active]
        else:
            alarms = [alarm]
        msg = 'The following alarms will be reseted:\n\t'+'\n\t'.join([t.tag for t in alarms])
        trace('In AlarmGUI.ResetAlarm(): %s'%msg)
        while len(cmt)==0:
            cmt, ok=prompt.getText(self,'Input dialog',msg+'\n\n'+'Must type a comment to continue:')
            if not ok: return
        comment=get_user()+': '+cmt
        for alarm in alarms:
            try: alarm.reset(comment) #It also tries to reset hidden alarms
            except: trace(traceback.format_exc())
        self.emitValueChanged()
        self.onFilter()

    def AcknowledgeAlarm(self,alarm=None):
        """THIS METHOD IS NEVER CALLED!?!?!?!?!?!?!"""
        alarm = alarm or self._currentAlarm
        trace('In AlarmGUI.AcknowledgeAlarm(%s)' % (alarm.tag))
        comment, ok = QtGui.QInputDialog.getText(self,'Input dialog','Type a comment to continue:')
        comment = get_user()+': '+comment
        if ok and len(str(comment)) != 0:
            try:
                alarm.reset(comment) #... Why it resets instead of Acknowledge?
                #taurus.Device(alarm.device).command_inout('Acknowledge',[tag, comment])
            except:
                trace(traceback.format_exc())
            self.onFilter()
        elif ok and len(str(comment)) < 3:
            self.AcknowledgeAlarm()
        [f.setAlarmData() for f in WindowManager.WINDOWS if isinstance(f,AlarmForm)]        
        
    def onAckStateChanged(self,checked=False):
        items = self.getSelectedRows(extend=False)
        if not len([i.alarmAcknowledged for i in items]) in (len(items),0):
            #if not target: 
            trace('onAckStateChanged(%s): nothing to do ...'%len([i.alarmAcknowledged for i in items]))
            return
        trace('onAckStateChanged(%s)'%[r.get_alarm_tag() for r in items])
        waiting=threading.Event()
        checked = not all([i.alarmAcknowledged for i in items])
        if checked:
            prompt=QtGui.QInputDialog
            while 1:
                cmt, ok=prompt.getText(self,'Input dialog','This will prevent reminders from sending.\nType a comment to continue:')
                if not ok: 
                    #Clean up the checkbox
                    #self.setCheckBox(self._dataWidget._wi.ackCheckBox,items[0].alarmAcknowledged)
                    break
                else:
                    comment=get_user()+': '+cmt
                    if len(str(cmt)) > 0:
                        for a in items:
                            try:
                                trace('\tacknowledging '+a.get_alarm_tag())
                                taurus.Device(a.get_alarm_object().device).command_inout('Acknowledge',[str(a.get_alarm_tag()), str(comment)])
                                waiting.wait(0.2)
                            except: print traceback.format_exc()
                        break
                    #self.setCheckBox(self._dataWidget._wi.ackCheckBox,True)
        else:
            for a in items:
                try:
                    trace('\trenouncing '+a.get_alarm_tag())
                    taurus.Device(a.get_alarm_object().device).command_inout('Renounce',str(a.get_alarm_tag()))
                    waiting.wait(0.2)
                except: trace( traceback.format_exc())
            #self.setCheckBox(self._dataWidget._wi.ackCheckBox,False)
        [o.get_acknowledged(force=True) for o in items]
        [f.setAlarmData() for f in WindowManager.WINDOWS if isinstance(f,AlarmForm)]
        self.onFilter()

    def onDisStateChanged(self,checked=False):
        items = self.getSelectedRows(extend=False)
        trace( 'onDisStateChanged(%s)'%[r.get_alarm_tag() for r in items])
        print list((i.get_alarm_tag(),i.alarmDisabled) for i in items)
        if len(set(bool(i.alarmDisabled) for i in items))!=1:
            q = Qt.QMessageBox.warning(self,"Warning!",'Not all elements selected have the same state')
            return
        waiting=threading.Event()
        checked = not all([i.alarmDisabled for i in items])
        if checked:
            reply=Qt.QMessageBox.question(self,"Warning!","Alarm will be disabled.\nDo you want to continue?\n"+'\n'.join(i.get_alarm_tag() for i in items),
                QtGui.QMessageBox.Yes | QtGui.QMessageBox.No, QtGui.QMessageBox.Yes)
            if reply == QtGui.QMessageBox.Yes:
                self.setAllowedUsers(self.api.get_admins_for_alarm(len(items)==1 and items[0].get_alarm_tag()))
                if not self.validate('onDisable/Enable(%s,%s)'%(checked,[a.get_alarm_tag() for a in items])):
                    return
                
                comment='DISABLED by '+get_user()
                for a in items:
                    try:
                        trace('\tdisabling '+a.get_alarm_tag())
                        taurus.Device(a.get_alarm_object().device).command_inout('Disable',[str(a.get_alarm_tag()), str(comment)])
                        waiting.wait(0.2)
                    except: trace(traceback.format_exc())
                
            else: return
        else:
            for a in items:
                try:
                    trace('\tenabling '+a.get_alarm_tag())
                    taurus.Device(a.get_alarm_object().device).command_inout('Enable',str(a.get_alarm_tag()))
                    waiting.wait(0.2)
                except: trace(traceback.format_exc())
        [o.get_disabled(force=True) for o in items]
        [f.setAlarmData() for f in WindowManager.WINDOWS if isinstance(f,AlarmForm)]
        self.onFilter()
        
    
        
class AlarmRowList(object):
  
    #def setRowModels(self):
        ##NEVER CALLED!
        #trace('AlarmGUI.setRowModels()')
        #for alarm in self.getAlarms():
            #self.AlarmRows[alarm.tag].setAlarmModel(alarm)

    def setAlarmRowModel(self,nr,obj,alarm,use_list):
        #print '%d/%d rows, %d models' % (nr,len(self.AlarmRows),len(taurus.Factory().tango_attrs.keys()))
        obj.setAlarmModel(alarm,use_list)
        self.updateStatusLabel()

    #def show(self):
        #print '---------> show()'
        #PARENT_CLASS.show(self)
        
    def checkAlarmRows(self):
      
        if self.api.keys():
            AlarmRow.TAG_SIZE = 1+max(len(k) for k in self.api.keys())
            
        #Removing deleted/renamed alarms
        for tag in self.AlarmRows.keys():
            if tag not in self.api:
                self.removeAlarmRow(tag)        
    
    def removeAlarmRow(self,alarm_tag):
        #Removing listeners to this alarm attribute
        trace('In removeAlarmRow(%s)'%alarm_tag)
        try:
            row = self.AlarmRows.pop(alarm_tag)
            ta = taurus.Attribute(row.getModel())
            ta.removeListener(row)
            row.setModel(None)
        except:
            trace('Unable to %s.removeListener():\n\t%s'%(alarm_tag,traceback.format_exc()))    
    
    def init_models(self):
        trace('Set Models thread ...')
        #self.connectAll()
        #self.buildList()
        self._connected = False
        self.modelsQueue = Queue.Queue()
        self.modelsThread = fn.qt.TauEmitterThread(
          parent=self,queue=self.modelsQueue,method=self.setAlarmRowModel)
        self.modelsThread.start()
        
    def buildRowList(self):
      
        l = [a for a in self.findListSource() if a.severity.lower() in self.severities]
        l = [getattr(self.AlarmRows.get(a.tag,None),'alarm',None) or a for a in l]
        if (self.regEx!=None): 
            trace('\tFiltering by regEx: %s'%self.regEx)
            l=self.regExFiltering(l)
        if str(self._ui.comboBoxx.currentText()) != 'ALL': 
            l=self.filterByState(l)
        
        #print '\tSorting %d alarms ...'%len(l)
        qualities = dict((x,self.alarmSorter(x)) for x in l)
        ordered = filter(bool,sorted(l,key=(lambda x: qualities[x])))
        if len(ordered)!=len(self.view.ordered): 
            print('Length of alarm list changed; changed = True')
            self.changed = True
        #print '\tAlarms in list are:\n'+'\n'.join(('\t\t%s;%s'%(x,qualities[x])) for x in ordered)
        
        #Updating alarms from api
        for nr, alarm in list(enumerate(ordered)):
            if not self.changed and self._ordered[nr]!=alarm: 
                trace('\tRow %s moved; changed = True'%alarm.tag)
                self.changed = True
            if alarm is None:
                trace('\tEmpty alarm found at %d'%nr)
                continue
            if alarm.tag not in self.AlarmRows:
                #print '\t%s,%s,%s: Creating AlarmRow ...'%(alarm.tag,bool(alarm.active),alarm.get_quality())
                row = self.AlarmRows[alarm.tag] = AlarmRow(api=self.api,qtparent=self)
                trace('\tNew alarm: %s; changed = True'%alarm.tag)
                try: 
                    self.modelsQueue.put((nr,row,alarm,(len(ordered)>self.MAX_ALARMS)))
                    #self.AlarmRows[alarm.tag].setAlarmModel(alarm,use_list=(len(self.ordered)>MAX_ALARMS))
                    self.changed = True
                except Exception,e: trace('===> AlarmRow.setModel(%s) FAILED!: %s' %(alarm.tag,e))
            else:
                row = self.AlarmRows[alarm.tag]
                try:
                    model = AttributeNameValidator().getUriGroups(row.getModel())
                    olddev = model['devname'] if model else None
                except:
                    #Taurus 3
                    #traceback.print_exc()
                    model = AttributeNameValidator().getParams(row.getModel())
                    olddev = model['devicename'] if model else None
                if alarm.device != olddev:
                    trace('\t%s device changed: %s => %s; changed = True'%(alarm.tag,alarm.device,olddev))
                    self.modelsQueue.put((nr,row,alarm,(len(ordered)>self.MAX_ALARMS)))
                    self.changed = True
                    
        if self.changed: self._ordered = ordered
        if self.modelsQueue.qsize(): 
            self.modelsThread.next()
            
    def findListSource(self, dev=None):
        combo1, combo2 = str(self._ui.contextComboBox.currentText()), str(self._ui.comboBoxx.currentText())
        #print "findListSource(%s,%s), filtering ..."%(combo1,combo2)
        self.timeSortingEnabled=None
        self.source = combo1
        alarms = self.getAlarms()
        if self.source == "Devices":
            self._alarmsList = self.api.get(device=combo2,alarms=alarms) if combo2 else []
        elif self.source == 'Receiver':
            self._alarmsList = self.api.get(receiver=combo2,alarms=alarms) if combo2 else []
        elif self.source == 'Severity':
            self._alarmsList = self.api.filter_severity(combo2,alarms=alarms)
        elif self.source == 'Hierarchy':
            self._alarmsList = self.api.filter_hierarchy(combo2,alarms=alarms)
        elif self.source == 'Time':
            self.timeSortingEnabled=combo2
        else:
            self._alarmsList = alarms

        self.api.servers.states()
        failed = [s.lower() for s in self.api.servers if self.api.servers[s].state is None]
        if failed:
            pass #trace('findListSource(%s,%s): %d servers are not running: %s'%(combo1, combo2,len(failed),failed))
        
        #timeSorting Filter moved to showList() method
        #self._alarmsList = [a for a in self._alarmsList if not self.timeSortingEnabled or self.api.servers.get_device_server(a.device).lower() not in failed]
        #print '\tfiltering done, returning %d/%d alarms'%(len(self._alarmsList),len(self.api.alarms.keys()))
        return self._alarmsList

    def filterByState(self, source):
        result=[]
        stateFilter=self._ui.comboBoxx.currentText()
        for a in source:
            if stateFilter=='AVAILABLE':
                if a.tag in self.AlarmRows and (str(self.AlarmRows[a.tag].quality) in ['ATTR_VALID', 'ATTR_ALARM', 'ATTR_CHANGING', 'ATTR_WARNING']): result.append(a)
            elif stateFilter=='FAILED':
                if a.tag not in self.AlarmRows or (str(self.AlarmRows[a.tag].quality) == 'ATTR_INVALID'): result.append(a)
            elif stateFilter=='HISTORY':
                if not self.snapi: 
                  self.snapi = get_snap_api()
                if self.snapi:
                  self.ctx_names = [c.name for c in self.snapi.get_contexts().values()]
                  if SNAP_ALLOWED and a.tag in self.ctx_names: result.append(a)
            else:
                result.append(a)
        trace('filterByState(%d): %d alarms returned'%(len(source),len(result)))
        return result

    def alarmSorter(self,obj):
        """obj is a panic.Alarm object """
        #Quality/Value should be managed by EventReceived, not read here!
        quality = obj.get_quality()
        if obj.tag in self.AlarmRows and self.AlarmRows[obj.tag].alarm is not None:
            row =  self.AlarmRows[obj.tag]
            if row.alarm.active!=obj.active:
                print '>'*80
                trace('ALARM API NOT UPDATED? : %s vs %s ' %(obj,row.alarm))
                print '>'*80
            acknowledged,disabled,active = row.alarmAcknowledged,row.alarmDisabled,row.alarm.active
            if self.AlarmRows[obj.tag].quality == ft.ATTR_INVALID: #It will update only INVALID ones, the rest will keep DB severity
                quality = ft.ATTR_INVALID
        else: acknowledged,disabled,active,quality = False,False,False,ft.ATTR_INVALID #Not updated will be invalid

        ACT = 0 if disabled else (-2 if (acknowledged and active) else (-1 if obj.active else 1))

        if self.timeSortingEnabled:
            #Ordered by active first, then time ASC, then name
            sorting = self._ui.comboBoxx.currentText()
            date = self.AlarmRows[obj.tag].get_alarm_time()
            return (-1*date if sorting=='DESC' else date, obj.tag)
        else:
            #Ordered by active first, then severity, then active time, then name
            if quality==ft.ATTR_ALARM:
                return (ACT, 0, obj.active, obj.tag)
            elif quality==ft.ATTR_WARNING:
                return (ACT, 1, obj.active, obj.tag)
            elif quality==ft.ATTR_VALID:
                return (ACT, 2, obj.active, obj.tag)
            elif quality==ft.ATTR_INVALID:
                return (ACT, 3, obj.active, obj.tag)            

class AlarmRow(QtGui.QListWidgetItem,TaurusBaseComponent):
    ALL_ROWS = {}
    MAX_ERRORS = 3
    TAG_SIZE = 45
    DATE_SIZE = len('Thu May 24 13:29:50 2012')
    
    def __init__(self,api,qtparent,tauparent=None):
        QtGui.QListWidgetItem.__init__(self)
        TaurusBaseComponent.__init__(self,tauparent)
        self.api = api
        self.qtparent = qtparent
        self.alarm = None
        self.alarmDisabled = None
        self.alarmAcknowledged = None
        self.font=QtGui.QFont(QtCore.QString("Courier"))
        self.font.setPointSize(10)
        self.setFont(self.font)
        self.errors = 0
        self.status = ''
        self.changed = False #This flag should be kept until updateStyle is called!!!
        
        self.quality = None
        self.setTextAlignment(Qt.Qt.AlignLeft)

    def __repr__(self):
        if self.alarm:
          return 'AlarmRow(%s):active=%s;quality=%s;errors=%s'%(self.alarm.tag,self.alarm.active,self.quality,self.errors)
        else:
          return 'AlarmRow(): not initialized'

    def setAlarmModel(self,alarm_object,use_list=True):
        """
        That's the place where you tell taurus to send the events to that object
        """
        #print 'AlarmRow(%s).setAlarmModel(%s)'%(self.getModel(),alarm_object)
        self.device = alarm_object.device
        self.use_list = use_list
        self.setModel(None)
        if use_list: self.model = alarm_object.device+'/'+'ActiveAlarms' 
        else: self.model = alarm_object.device+'/'+alarm_object.get_attribute()
        #print'In AlarmRow(%s).setModel(%s,use_list=%s)'%(alarm_object.tag, self.model,use_list)
        
        self.alarm = alarm_object
        self.tag = alarm_object.tag
        self.alarm.counter = -1
        self.errors = 0
        self.alarm.active = None
        self.quality = None
        AlarmRow.ALL_ROWS[str(self.tag).lower()] = self
        self.setText('  '+self.get_tag_text()+' - loading ...')
        try: taurus.Device(alarm_object.device).set_timeout_millis(DEVICE_TIMEOUT)
        except: print(fandango.log.except2str())
        self.setModel(self.model)
        taurus.Attribute(self.model).changePollingPeriod(REFRESH_TIME)

    def get_alarm_tag(self):
        return self.tag
    
    def get_tag_text(self):
        return ('%'+'%d'%self.TAG_SIZE+'s')%self.alarm.tag[:self.TAG_SIZE]

    def get_alarm_object(self):
        return self.qtparent.api[self.tag]

    def get_acknowledged(self,force=False):
        val = None
        try:
            if not force and self.use_list: 
                if not getattr(self,'ack_attr',None):
                    self.ack_attr = taurus.Attribute(self.device+'/AcknowledgedAlarms')
                    self.ack_attr.changePollingPeriod(REFRESH_TIME)
                ack_val = getAttrValue(self.ack_attr.read())
                val = any([a==self.alarm.tag for a in (ack_val or [])])
            else: 
                val = taurus.Device(self.alarm.device).command_inout('CheckAcknowledged',self.alarm.tag)
                if force: 
                    self.alarmAcknowledged = val
        except:
            print fandango.log.except2str()
        #print 'In AlarmRow(%s).get_acknowledged(): %s'%(self.alarm.tag,val)
        return val
        
    def get_disabled(self,force=False):
        val = None
        try:
            if not force and self.use_list: 
                if not getattr(self,'dis_attr',None):
                    self.dis_attr = taurus.Attribute(self.device+'/DisabledAlarms')
                    self.dis_attr.changePollingPeriod(REFRESH_TIME)
                dis_val = getAttrValue(self.dis_attr.read())
                val = any(re.split('[: ,;]',a)[0]==self.alarm.tag for a in (dis_val or []))
            else: 
                val = taurus.Device(self.alarm.device).command_inout('CheckDisabled',self.alarm.tag)
                if force: self.alarmDisabled = val
        except:
            print fandango.log.except2str()
        #print 'In AlarmRow(%s).get_disabled(): %s'%(self.alarm.tag,val)
        return val
        
    def get_alarm_time(self, alarm=None, attr_value=None, null = float('nan')):
        alarm = alarm or self.alarm
        try:
            if not self.alarm.active:
                self.alarm.active = getAlarmTimestamp(alarm)
            #print 'AlarmRow(%s).get_alarm_date(%s)'%(alarm.tag,alarm.active)
            return self.alarm.active if self.alarm.active else 0
        except:
            print traceback.format_exc()
        return fandango.END_OF_TIME if self.alarm.active else 0
        
    def get_alarm_date(self, alarm=None, attr_value=None, null = ' NaN '):
        try:
            return ('%'+str(self.DATE_SIZE)+'s')%fandango.time2str(self.get_alarm_time(alarm,attr_value))
        except:
            print traceback.format_exc()
            return str(null)
            
    def eventReceived(self,evt_src,evt_type,evt_value):
        try:
            debug = 'debug' in str(evt_src).lower() or TRACE_LEVEL>0
            now = fandango.time2str()
            evtype = str(TaurusEventType.reverseLookup[evt_type])
            # Direct getattr(o,n,v) fails on some taurus classes
            is_empty = (hasattr(evt_value,'is_empty') and getattr(evt_value,'is_empty')) or False
            evvalue = getAttrValue(evt_value) if not is_empty else []
            
            if debug: 
                print '\n'
                trace('%s: In AlarmRow(%s).eventReceived(%s,%s,%s)'%(fandango.time2str(),self.alarm.tag,evt_src,evtype,evvalue),clean=True)
            disabled,acknowledged,quality,value = self.alarmDisabled,self.alarmAcknowledged,self.quality,bool(evvalue) #bool(self.alarm.active)
            if self.qtparent and getattr(self.qtparent,'api',None): self.alarm = self.qtparent.api[self.tag] #Using common api object
            
            #Ignoring Config Events
            if evt_type==TaurusEventType.Config:
                if debug: trace('%s: AlarmRow(%s).eventReceived(CONFIG): %s' % (now,self.alarm.tag,str(evt_value)[:20]),clean=True)
                return

            #Filtering Error Events
            elif evt_type==TaurusEventType.Error or evvalue is None:
                error = True
                self.errors+=1
                if self.errors>=self.MAX_ERRORS: 
                    #After MAX_ERRORS the alarm is simply ignored
                    self.alarm.active,self.quality = None,PyTango.AttrQuality.ATTR_INVALID
                if not self.errors%self.MAX_ERRORS:
                    if 'EventConsumer' not in str(evt_value): 
                        trace('%s: AlarmRow(%s).eventReceived(ERROR): %s' %(now,self.alarm.tag,'ERRORS=%s!:\n\t%s'%(self.errors,fandango.except2str(evt_value,80))),clean=True)
                    #if self.value is None: taurus.Attribute(self.model).changePollingPeriod(5*REFRESH_TIME)
                    if not self.changed and self.errors==self.MAX_ERRORS or 'Exception' not in self.status: 
                        print '%s : %s.emitValueChanged(ERROR!)'%(now,self.alarm.tag)
                        print 'ERROR: %s(%s)' % (type(evt_value),clean_str(evt_value))
                        self.qtparent.emitValueChanged()
                        self.changed = True #This flag is set here, and set to False after updating row style
                        self.updateStyle(event=True,error=fandango.except2str(evt_value)) #It seems necessary to update the row text, color and icon
                else: 
                    if debug: trace('In AlarmRow(%s).eventReceived(%s,%s,%d/%d)' % (self.alarm.tag,evt_src,evtype,self.errors,self.MAX_ERRORS),clean=True)
                    pass

            #Change Events
            elif evt_type==TaurusEventType.Change or evt_type==TaurusEventType.Periodic:
                self.errors = 0
                
                # Refresh period not changed as these lines slows down a lot!!
                #ta = taurus.Attribute(self.model)
                #if self.value is None: ta.changePollingPeriod(5*REFRESH_TIME)
                #elif ta.getPollingPeriod()!=REFRESH_TIME: ta.changePollingPeriod(REFRESH_TIME)
                
                disabled = self.get_disabled()
                acknowledged = self.get_acknowledged()
                if str(self.model).endswith('/ActiveAlarms'):
                    value,quality = any(s.startswith(self.alarm.tag+':') for s in (evvalue or [])),self.alarm.get_quality()
                else:
                    value,quality = evvalue,evt_value.quality
                
                if debug: trace('In AlarmRow(%s).eventReceived(%s,%s,%s)' % (self.alarm.tag,evt_src,str(TaurusEventType.reverseLookup[evt_type]),evvalue),clean=True)
                if debug: trace('\t%s (%s), dis:%s, ack:%s'%(value,quality,disabled,acknowledged))
                
                if  value!=bool(self.alarm.active) or quality!=self.quality or disabled!=self.alarmDisabled or acknowledged!=self.alarmAcknowledged:
                    if not self.changed: 
                        #print '%s : %s.emitValueChanged(%s)'%(fandango.time2str(),self.alarm.tag,value)
                        self.qtparent.emitValueChanged()
                    self.changed = True #This flag is set here, and set to False after updating row style
                
                self.alarmDisabled = disabled
                self.alarmAcknowledged = acknowledged
                self.quality = quality
                self.alarm.active = getAlarmTimestamp(self.alarm) if value else 0 #It will get the date from ActiveAlarms array
                
                if debug: trace('\tactive since %s'%time2str(self.alarm.active))
                
                self.updateStyle(event=True,error=False)
            else: 
                print '\tUnknown event type?!? %s' % evt_type
        except:
            try: print 'Exception in eventReceived(%s,...): \n%s' %(evt_src,fandango.log.except2str())
            except : print 'eventReceived(...)!'*80+'\n'+traceback.format_exc()
        if debug: print '\n'
            
    def updateIfChanged(self):
        if self.changed:
            print 'AlarmRow(%s).updateIfChanged(changed=True)'%(self.alarm.tag)
            self.updateStyle(event=True,error=self.errors>self.MAX_ERRORS)
            self.changed = False

    def updateStyle(self,event=False,error=False):
        #trace('%s -> AlarmRow(%s).updateStyle(event=%s)'%(time.ctime(),self.alarm.tag,event),clean=True)
        if getattr(self.qtparent,'_attributesSignalsBlocked',False):
            #print '\tupdateStyle(): blocked!'
            return
        if event:
            try:
                self.font=QtGui.QFont(QtCore.QString("Courier"))
                self.font.setPointSize(10)
                if error:
                    if self.errors>=self.MAX_ERRORS and not self.errors%self.MAX_ERRORS:
                        self.was_ok = self.alarm.active or self.alarm.recovered
                        self.alarm.active,self.alarm.recovered,self.alarm.counter = 0,0,0
                        self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,None,False,QtGui.QColor("grey").light(),QtGui.QColor("white"))
                        if self.was_ok:
                            self.font.setBold(False)
                        error_text = clean_str(error if isinstance(error,basestring) else 'disabled').split('=',1)[-1].strip()[:40]
                        self.setText('   '+' - '.join((self.get_tag_text(),error_text)))
                        self.status = 'Exception received, check device %s'%self.alarm.device
                elif self.alarm.active is None:
                    #trace('updateStyle(%s): value not received yet' %(self.alarm.tag),clean=True)
                    pass
                else:
                    trace('AlarmRow.updateStyle: %s = %s (%s)' %(self.alarm.tag,self.alarm.active,self.quality),clean=True)
                    if self.alarm.active and not self.alarmDisabled:
                        if self.quality==PyTango.AttrQuality.ATTR_ALARM:
                            trace('alarm')
                            if self.alarmAcknowledged:
                                self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"media-playback-pause",False,QtGui.QColor("black"),QtGui.QColor("red").lighter())
                            else:
                                self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"software-update-urgent",False,QtGui.QColor("black"),QtGui.QColor("red").lighter())
                        elif self.quality==PyTango.AttrQuality.ATTR_WARNING:
                            trace('warning')
                            if self.alarmAcknowledged:
                                self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"media-playback-pause",False,QtGui.QColor("black"),QtGui.QColor("orange").lighter())
                            else:
                                self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"emblem-important",False,QtGui.QColor("black"),QtGui.QColor("orange").lighter())
                        elif self.quality==PyTango.AttrQuality.ATTR_VALID:
                            trace('debug')
                            if self.alarmAcknowledged:
                                self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"media-playback-pause",False,QtGui.QColor("black"),QtGui.QColor("yellow").lighter())
                            else:
                                self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"applications-development",False,QtGui.QColor("black"),QtGui.QColor("yellow").lighter())
                        else: 
                            print '\tUnknown event quality?!? %s' % self.quality
                            
                        if self.alarm.counter<2:
                            self.font.setBold(True)
                        self.alarm.recovered,self.alarm.counter = 0,2

                        #else: self.font.SetBold(False) #Good to keep it, to see what changed
                        self.status = 'Alarm Acknowledged, no more messages will be sent' if self.alarmAcknowledged else 'Alarm is ACTIVE'
                        self.setText(' | '.join((self.get_tag_text(),self.get_alarm_date(), self.alarm.description)))
                        #self.setText('%45s | %30s'%(str(self.alarm.tag)[:45], self.get_alarm_date(), self.alarm.description))

                    elif self.alarm.active in (False,0) and not self.alarmDisabled:
                        if self.alarmAcknowledged:
                            self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"media-playback-pause",False,QtGui.QColor("green").lighter(),QtGui.QColor("white"))
                        else:
                            self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"emblem-system",False,QtGui.QColor("green").lighter(),QtGui.QColor("white"))
                        if not self.alarm.recovered:
                            #trace('\teventReceived(%s): %s => %s' %(self.alarm.tag,self.alarm.active,self.value),clean=True)
                            if self.alarm.counter>1: 
                                self.font.setBold(True)
                            self.alarm.active,self.alarm.recovered,self.alarm.counter = 0,time.time(),1
                        #else: self.font.SetBold(False) #Good to keep it, to see what changed
                        self.status = 'Alarm has NOT been triggered'
                        self.setText(' - '.join((self.get_tag_text(),'Not triggered')))

                    else: #AlarmDisabled or value = None
                        self.status = 'Alarm is Disabled, status will not be updated'
                        self.qtparent.emit(QtCore.SIGNAL('setfontsandcolors'),self.tag,"dialog-error",False,QtGui.QColor("black"),QtGui.QColor("grey").lighter())
                        
                    #if self.qtparent.USE_EVENT_REFRESH: 
                self.setToolTip('\n'.join([
                    self.status,'',
                    'Severity: '+self.alarm.severity,
                    'Formula: '+self.alarm.formula,
                    'Description: %s'%self.alarm.description,
                    'Alarm Device: %s'%self.alarm.device,
                    'Archived: %s'%('Yes' if 'SNAP' in self.alarm.receivers else 'No'),
                    ]))
                self.setFont(self.font)
            except:
                print 'Exception in updateStyle(%s,...): \n%s' %(self.alarm.tag,traceback.format_exc())
        else:
            for klass in type(self).__bases__:
                try: 
                    if hasattr(klass,'updateStyle'): klass.updateStyle(self)
                except: pass

        pass
            
    @classmethod
    def setFontsAndColors(klass,tag,icon,bold,color,background):
        #print 'setFontsAndColors(%s,%s,%s,%s,%s)'%(tag,icon,bold,color.name(),background.name())
        tag = str(tag).lower()
        if tag in klass.ALL_ROWS:
            self = klass.ALL_ROWS[tag]
            self.alarmIcon=getThemeIcon(icon) if icon else None
            self.setIcon(self.alarmIcon or Qt.QIcon())
            self.font.setBold(bold)
            self.setTextColor(color)
            self.setBackgroundColor(background)
        else:
            print 'Tag %s is not in the list of AlarmRows: %s' % (tag,klass.ALL_ROWS.keys())
