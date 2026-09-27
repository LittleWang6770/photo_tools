"""Native Cocoa interface; processing stays in the shared CLI engine."""
import argparse
import json
import os
from pathlib import Path
import threading
import time
import traceback

import objc
from AppKit import (NSApplication, NSApplicationActivationPolicyRegular, NSAppearance,
    NSAppearanceNameAqua, NSBackingStoreBuffered, NSBezelStyleRounded, NSBox, NSBoxCustom,
    NSButton, NSButtonTypeSwitch, NSColor, NSFont, NSFontWeightSemibold, NSImage, NSImageView,
    NSLineBreakByTruncatingMiddle, NSMenu, NSMenuItem, NSModalResponseOK, NSNoTitle,
    NSOffState, NSOnState, NSOpenPanel, NSPNGFileType, NSPopUpButton, NSProgressIndicator,
    NSTextAlignmentCenter, NSTextField, NSTerminateCancel, NSTerminateLater, NSTerminateNow,
    NSWindow, NSWindowStyleMaskClosable, NSWindowStyleMaskMiniaturizable, NSWindowStyleMaskTitled,
    NSWorkspace)
from Foundation import NSObject, NSMakeRect, NSTimer, NSURL

from .cli import execute, read_gps, has_coordinates, coordinate_values, recommended_workers, format_duration
from .runtime import ROOT, FROZEN, exiftool_path


class Controller(NSObject):
    def applicationDidFinishLaunching_(self, notification):
        self.template_path = self.directory_path = None
        self.template_valid = self.busy = self.quit_pending = False
        self.stop_event = threading.Event()
        self.last_result = None
        self.eta_deadline = None
        self.last_completed = self.total = 0
        self.available_cpus = min(32, os.cpu_count() or 1)
        self.default_workers = recommended_workers(self.available_cpus)
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0,0,720,760), NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
            NSWindowStyleMaskMiniaturizable, NSBackingStoreBuffered, False)
        self.window.setTitle_('照片 GPS 复制')
        self.window.setAppearance_(NSAppearance.appearanceNamed_(NSAppearanceNameAqua))
        self.window.setDelegate_(self)
        self.window.setReleasedWhenClosed_(False)
        self.window.setBackgroundColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(.965,.978,.977,1))
        self.window.center()
        view = self.window.contentView()
        view.setWantsLayer_(True)
        view.layer().setBackgroundColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(.965,.978,.977,1).CGColor())
        icon = NSImageView.alloc().initWithFrame_(NSMakeRect(330,688,60,60))
        icon.setImage_(NSImage.alloc().initWithContentsOfFile_(str(ROOT / ('assets/gps-copy.png' if FROZEN else 'macos/assets/gps-copy.png'))))
        view.addSubview_(icon)
        self.label('照片 GPS 复制', (40,642,640,36), 26, strong=True, center=True)
        self.label('用一张照片的位置，为整批照片补上 GPS', (40,612,640,24), 14, center=True)
        self.card((32,488,656,108))
        self.label('1  GPS 来源照片', (52,562,470,24), 15, strong=True)
        self.template_label = self.label('选择一张带 GPS 的 JPG / JPEG', (52,534,464,23), 13)
        self.template_label.cell().setLineBreakMode_(NSLineBreakByTruncatingMiddle)
        self.coordinates = self.label('仅复制经纬度与方向，不改变图像内容。', (52,504,608,22), 12)
        self.template_button = self.button('选择照片…', 'chooseTemplate:', (532,530,136,34))
        self.card((32,370,656,104))
        self.label('2  待处理照片目录', (52,442,470,24), 15, strong=True)
        self.directory_label = self.label('选择需要写入 GPS 的文件夹', (52,414,464,23), 13)
        self.directory_label.cell().setLineBreakMode_(NSLineBreakByTruncatingMiddle)
        self.label('包含子目录中的 JPG / JPEG，跳过来源照片、隐藏目录和备份。', (52,386,608,22), 12)
        self.directory_button = self.button('选择文件夹…', 'chooseDirectory:', (532,410,136,34))
        self.card((32,246,656,112))
        self.label('已有 GPS 时', (52,328,365,22), 13, strong=True)
        self.mode_picker = self.popup(['跳过，不改变已有位置', '覆盖原图的 GPS 位置'], (48,290,370,32))
        self.mode_picker.setTarget_(self);self.mode_picker.setAction_('optionsChanged:')
        self.mode_hint = self.label('没有 GPS 的照片仍会写入来源位置。', (52,261,365,22), 11)
        self.label('CPU 并发数', (456,328,212,22), 13, strong=True)
        self.workers_picker = self.popup([f'自动 · {self.default_workers} 个任务（推荐）'] +
            [str(i) for i in range(1,self.available_cpus+1)], (452,290,220,32))
        self.label(f'本机 {os.cpu_count() or 1} 个逻辑核心', (456,261,212,22), 11)
        self.backup = self.button('修改前备份原图（可选，额外占用空间）', 'optionsChanged:', (40,210,620,24))
        self.backup.setButtonType_(NSButtonTypeSwitch);self.backup.setState_(NSOffState)
        self.backup_hint = self.label('默认不备份：直接更新 GPS，不保留修改前副本；已有备份保持不变。', (44,182,632,23), 12)
        self.run_button = self.button('开始复制', 'runCopy:', (240,130,156,40))
        self.run_button.setKeyEquivalent_('\r');self.run_button.setEnabled_(False)
        self.stop_button = self.button('停止', 'stopCopy:', (412,130,80,40))
        self.stop_button.setEnabled_(False)
        self.progress = NSProgressIndicator.alloc().initWithFrame_(NSMakeRect(40,111,424,7))
        self.progress.setIndeterminate_(False);self.progress.setMinValue_(0);self.progress.setMaxValue_(100)
        view.addSubview_(self.progress)
        self.eta = self.label('剩余时间：等待运行', (474,100,208,24), 12, center=True)
        self.status = self.label('先选择 GPS 来源照片和待处理目录。', (40,58,640,40), 12, center=True)
        self.open_button = self.button('打开照片目录', 'openDirectory:', (40,18,140,28))
        self.open_backup_button = self.button('打开备份', 'openBackup:', (190,18,140,28))
        self.log_button = self.button('查看日志', 'openLog:', (540,18,140,28))
        self.open_button.setEnabled_(False);self.open_backup_button.setEnabled_(False)
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(1.,self,'refreshETA:',None,True)
        menu = NSMenu.alloc().init();item = NSMenuItem.alloc().init();menu.addItem_(item)
        app_menu = NSMenu.alloc().initWithTitle_('照片 GPS 复制')
        app_menu.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('退出照片 GPS 复制','terminate:','q'))
        item.setSubmenu_(app_menu);NSApplication.sharedApplication().setMainMenu_(menu)
        self.window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        if self.test_options:self.performSelector_withObject_afterDelay_('beginTest:',None,.5)

    @objc.python_method
    def label(self, text, rect, size, strong=False, center=False):
        value = NSTextField.labelWithString_(text);value.setFrame_(NSMakeRect(*rect))
        value.setFont_(NSFont.systemFontOfSize_weight_(size,NSFontWeightSemibold) if strong else NSFont.systemFontOfSize_(size))
        value.setTextColor_(NSColor.labelColor() if strong else NSColor.secondaryLabelColor())
        if center:value.setAlignment_(NSTextAlignmentCenter)
        self.window.contentView().addSubview_(value)
        return value

    @objc.python_method
    def card(self, rect):
        box=NSBox.alloc().initWithFrame_(NSMakeRect(*rect));box.setBoxType_(NSBoxCustom);box.setTitlePosition_(NSNoTitle)
        box.setCornerRadius_(12);box.setBorderWidth_(1)
        box.setBorderColor_(NSColor.colorWithCalibratedWhite_alpha_(.89,1));box.setFillColor_(NSColor.whiteColor())
        self.window.contentView().addSubview_(box)

    @objc.python_method
    def button(self, text, action, rect):
        value=NSButton.alloc().initWithFrame_(NSMakeRect(*rect));value.setTitle_(text)
        value.setBezelStyle_(NSBezelStyleRounded);value.setTarget_(self);value.setAction_(action)
        self.window.contentView().addSubview_(value)
        return value

    @objc.python_method
    def popup(self, titles, rect):
        value=NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(*rect),False)
        value.addItemsWithTitles_(titles);self.window.contentView().addSubview_(value)
        return value

    @objc.python_method
    def panel(self, directory):
        panel=NSOpenPanel.openPanel();panel.setAllowsMultipleSelection_(False)
        panel.setCanChooseFiles_(not directory);panel.setCanChooseDirectories_(directory)
        panel.setCanCreateDirectories_(False)
        panel.setTitle_('选择待处理照片目录' if directory else '选择 GPS 来源照片')
        panel.setPrompt_('选择文件夹' if directory else '选择照片')
        if not directory:panel.setAllowedFileTypes_(['jpg','jpeg'])
        previous=self.directory_path if directory else self.template_path
        if previous:panel.setDirectoryURL_(NSURL.fileURLWithPath_(str(Path(previous) if directory else Path(previous).parent)))
        return panel

    def chooseTemplate_(self, sender):
        if self.busy:return
        self.active_panel=self.panel(False)
        def selected(response):
            if response==NSModalResponseOK:self.set_template(self.active_panel.URL().path())
        self.active_panel.beginSheetModalForWindow_completionHandler_(self.window,selected)

    def chooseDirectory_(self, sender):
        if self.busy:return
        self.active_panel=self.panel(True)
        def selected(response):
            if response==NSModalResponseOK:self.set_directory(self.active_panel.URL().path())
        self.active_panel.beginSheetModalForWindow_completionHandler_(self.window,selected)

    @objc.python_method
    def set_template(self, path):
        self.template_path=str(Path(path).resolve());self.template_valid=False
        self.template_label.setStringValue_(self.template_path);self.template_label.setToolTip_(self.template_path)
        self.coordinates.setStringValue_('正在读取 GPS…');self.update_ready()
        current=self.template_path
        def inspect():
            try:
                metadata,error=read_gps(exiftool_path(),Path(current))
                if metadata is None:raise ValueError(error)
                if not has_coordinates(metadata):raise ValueError('这张照片没有完整 GPS，请选择其他来源照片。')
                lat,lon,ns,ew=coordinate_values(metadata)
                self.post({'kind':'template','path':current,'valid':True,'text':f'来源位置：{abs(lat):.6f}° {ns}  ·  {abs(lon):.6f}° {ew}'})
            except Exception as exc:self.post({'kind':'template','path':current,'valid':False,'text':str(exc)})
        threading.Thread(target=inspect,daemon=True,name='gps-source-check').start()

    @objc.python_method
    def set_directory(self, path):
        self.directory_path=str(Path(path).resolve())
        self.directory_label.setStringValue_(self.directory_path);self.directory_label.setToolTip_(self.directory_path)
        self.open_button.setEnabled_(True)
        self.open_backup_button.setEnabled_((Path(self.directory_path)/'.batch-gps-copy-backup').is_dir())
        self.update_ready()

    @objc.python_method
    def update_ready(self):
        ready=self.template_valid and self.directory_path is not None and not self.busy
        self.run_button.setEnabled_(bool(ready))
        if ready:self.status.setStringValue_('准备就绪。将直接更新目标照片的 GPS，来源照片保持不变。')

    def optionsChanged_(self, sender):
        self.mode_hint.setStringValue_('没有 GPS 的照片仍会写入来源位置。' if self.mode_picker.indexOfSelectedItem()==0 else '已有位置也会替换为来源照片的位置。')
        enabled = self.backup.state()==NSOnState
        self.backup_hint.setStringValue_('将额外保存完整原图，空间接近本次修改照片的总大小；重复写入会累积备份。' if enabled else '默认不备份：直接更新 GPS，不保留修改前副本；已有备份保持不变。')
        self.backup_hint.setTextColor_(NSColor.systemOrangeColor() if enabled else NSColor.secondaryLabelColor())
        self.backup_hint.setToolTip_('备份位于所选目录内的 .batch-gps-copy-backup；同名旧备份会保留。' if enabled else '关闭备份不会清理以前生成的备份。')

    def runCopy_(self, sender):
        if self.busy or not self.template_valid or not self.directory_path:return
        workers=self.workers_picker.indexOfSelectedItem() or self.default_workers
        args=argparse.Namespace(template_photo=Path(self.template_path),directory=Path(self.directory_path),
            force=self.mode_picker.indexOfSelectedItem()==1,no_backup=self.backup.state()!=NSOnState,
            workers=workers,exiftool='exiftool')
        self.busy=True;self.last_result=None;self.stop_event.clear();self.eta_deadline=None
        self.progress.setDoubleValue_(0);self.eta.setStringValue_('剩余时间：准备中…')
        for control in (self.template_button,self.directory_button,self.mode_picker,self.workers_picker,self.backup,self.run_button):control.setEnabled_(False)
        self.stop_button.setEnabled_(True)
        if self.test_options:self.test_run_options={'force':args.force,'backup':not args.no_backup,'workers':workers}
        def work():
            try:execute(args,event_callback=self.post,stop_event=self.stop_event)
            except Exception as exc:
                traceback.print_exc();self.post({'kind':'error','message':str(exc)})
            finally:self.post({'kind':'idle'})
        threading.Thread(target=work,daemon=False,name='gps-copy').start()

    @objc.python_method
    def post(self, event):
        with objc.autorelease_pool():self.performSelectorOnMainThread_withObject_waitUntilDone_('receive:',event,False)

    def receive_(self, event):
        kind=event['kind']
        if kind=='template':
            if event['path']!=self.template_path:return
            self.template_valid=event['valid'];self.coordinates.setStringValue_(event['text'])
            self.coordinates.setToolTip_(event['text']);self.update_ready()
            if self.test_options and getattr(self,'test_waiting',False):self.performSelector_withObject_afterDelay_('runTest:',None,.2)
        elif kind=='preparing':self.status.setStringValue_('正在检查来源 GPS 并扫描照片目录…')
        elif kind=='started':
            self.total=event['total'];self.status.setStringValue_(f'找到 {self.total} 张照片，正在处理…')
        elif kind=='progress':
            self.progress.setDoubleValue_(100*event['completed']/event['total'])
            self.last_completed=event['completed'];self.eta_deadline=time.monotonic()+event['remaining']
            self.refreshETA_(None)
            self.status.setStringValue_(f'{event["completed"]} / {event["total"]}  ·  写入 {event["written"]}  ·  跳过 {event["skipped"]}  ·  失败 {event["failed"]}\n{event["file"]}')
            if self.test_options and not getattr(self,'test_progress_snapshot',False):
                self.snapshot('running.png');self.test_progress_snapshot=True
        elif kind=='completed':
            self.last_result=dict(event);self.eta_deadline=None
            self.eta.setStringValue_('已停止' if event['cancelled'] else '已完成')
            backup_status = '已保留备份，可点击「打开备份」查看。' if event['backup'] else '本次未生成原图备份。'
            self.status.setStringValue_(f'{"已停止" if event["cancelled"] else "完成"}：写入 {event["written"]}，跳过 {event["skipped"]}，失败 {event["failed"]}。\n用时 {format_duration(event["seconds"])}；'+backup_status)
            self.open_backup_button.setEnabled_(Path(event['backup_directory']).is_dir())
        elif kind=='empty':
            self.eta.setStringValue_('没有待处理照片');self.status.setStringValue_('目录中没有可处理的 JPG / JPEG，未修改任何照片。')
        elif kind=='error':
            self.eta_deadline=None;self.eta.setStringValue_('处理未完成')
            self.status.setStringValue_('未完成：'+event['message']);self.status.setToolTip_(event['message'])
        elif kind=='idle':
            self.busy=False
            for control in (self.template_button,self.directory_button,self.mode_picker,self.workers_picker,self.backup):control.setEnabled_(True)
            self.run_button.setEnabled_(bool(self.template_valid and self.directory_path));self.stop_button.setEnabled_(False)
            if self.quit_pending:NSApplication.sharedApplication().replyToApplicationShouldTerminate_(True)
            elif self.test_options:self.performSelector_withObject_afterDelay_('finishTest:',None,.4)

    def refreshETA_(self, sender):
        if self.busy and self.eta_deadline is not None and not self.stop_event.is_set():
            remaining=max(1 if self.last_completed<self.total else 0,self.eta_deadline-time.monotonic())
            self.eta.setStringValue_('剩余约 '+format_duration(remaining))

    def stopCopy_(self, sender):
        if not self.busy:return
        self.stop_event.set();self.stop_button.setEnabled_(False);self.eta.setStringValue_('正在停止…')
        self.status.setStringValue_('等待正在处理的照片完成；已写入的 GPS 和备份会保留。')

    def openDirectory_(self, sender):
        if self.directory_path:NSWorkspace.sharedWorkspace().openURL_(NSURL.fileURLWithPath_(self.directory_path))

    def openBackup_(self, sender):
        if self.directory_path:NSWorkspace.sharedWorkspace().openURL_(NSURL.fileURLWithPath_(str(Path(self.directory_path)/'.batch-gps-copy-backup')))

    def openLog_(self, sender):
        NSWorkspace.sharedWorkspace().openURL_(NSURL.fileURLWithPath_(str(self.log_path)))

    def windowShouldClose_(self, sender):
        if self.busy:self.stopCopy_(None);return False
        return True

    def applicationShouldTerminateAfterLastWindowClosed_(self, sender):return True

    def applicationShouldTerminate_(self, sender):
        if not self.busy:return NSTerminateNow
        self.quit_pending=True;self.stopCopy_(None);return NSTerminateLater

    @objc.python_method
    def snapshot(self, filename):
        self.window.displayIfNeeded();view=self.window.contentView()
        bitmap=view.bitmapImageRepForCachingDisplayInRect_(view.bounds())
        view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(),bitmap)
        bitmap.representationUsingType_properties_(NSPNGFileType,{}).writeToFile_atomically_(str(Path(self.test_options['output'])/filename),True)

    def beginTest_(self, sender):
        self.test_initial_backup=bool(self.backup.state()==NSOnState)
        self.test_panels={};self.snapshot('initial.png');self.chooseTemplate_(None)
        self.performSelector_withObject_afterDelay_('cancelPhotoTest:',None,.4)

    def cancelPhotoTest_(self, sender):
        self.test_panels['photo']={'native':isinstance(self.active_panel,NSOpenPanel),'files':bool(self.active_panel.canChooseFiles()),'directories':bool(self.active_panel.canChooseDirectories()),'multiple':bool(self.active_panel.allowsMultipleSelection())}
        self.active_panel.cancel_(None);self.chooseDirectory_(None)
        self.performSelector_withObject_afterDelay_('cancelFolderTest:',None,.4)

    def cancelFolderTest_(self, sender):
        self.test_panels['directory']={'native':isinstance(self.active_panel,NSOpenPanel),'files':bool(self.active_panel.canChooseFiles()),'directories':bool(self.active_panel.canChooseDirectories()),'multiple':bool(self.active_panel.allowsMultipleSelection())}
        self.active_panel.cancel_(None)
        self.mode_picker.selectItemAtIndex_(1 if self.test_options['force'] else 0)
        self.workers_picker.selectItemAtIndex_(self.test_options['workers'])
        if 'backup' in self.test_options:
            self.backup.setState_(NSOnState if self.test_options['backup'] else NSOffState)
        self.optionsChanged_(None);self.set_directory(self.test_options['directory'])
        self.test_waiting=True;self.set_template(self.test_options['template'])

    def runTest_(self, sender):
        self.test_waiting=False;self.snapshot('selected.png')
        if self.template_valid:self.run_button.performClick_(None)
        else:self.finishTest_(None)

    def finishTest_(self, sender):
        self.snapshot('completed.png')
        receipt={'panels':self.test_panels,'template_valid':self.template_valid,
                 'initial_backup':self.test_initial_backup,
                 'backup_hint':str(self.backup_hint.stringValue()),
                 'status':str(self.status.stringValue()),
                 'run_options':getattr(self,'test_run_options',None),'result':self.last_result,
                 'run_enabled':bool(self.run_button.isEnabled())}
        (Path(self.test_options['output'])/'gui-test.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
        NSApplication.sharedApplication().terminate_(None)


def run(argv, log_path):
    parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--ui-smoke',type=Path)
    args,_=parser.parse_known_args(argv)
    app=NSApplication.sharedApplication();app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    controller=Controller.alloc().init();controller.log_path=log_path
    controller.test_options=json.loads(args.ui_smoke.read_text()) if args.ui_smoke else None
    app.setDelegate_(controller);app.run()
