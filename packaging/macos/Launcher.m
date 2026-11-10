#import <Cocoa/Cocoa.h>

@interface DeskLauncher : NSObject <NSApplicationDelegate>
@property(nonatomic, strong) NSTask *server;
@property(nonatomic, strong) NSURL *address;
@end

@implementation DeskLauncher
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    NSMenu *main = [NSMenu new];
    NSMenuItem *root = [NSMenuItem new];
    [main addItem:root];
    NSMenu *menu = [[NSMenu alloc] initWithTitle:@"Desk"];
    NSMenuItem *open = [menu addItemWithTitle:@"Open Desk" action:@selector(openDesk:) keyEquivalent:@"o"];
    open.target = self;
    [menu addItem:[NSMenuItem separatorItem]];
    [menu addItemWithTitle:@"Quit Desk" action:@selector(terminate:) keyEquivalent:@"q"];
    root.submenu = menu;
    NSApp.mainMenu = main;
    [self openDesk:nil];
}

- (BOOL)applicationShouldHandleReopen:(NSApplication *)application hasVisibleWindows:(BOOL)visible {
    [self openDesk:nil];
    return YES;
}

- (void)openDesk:(id)sender {
    if (self.address && self.server.running) {
        [NSWorkspace.sharedWorkspace openURL:self.address];
        return;
    }
    if (self.server.running) return;
    self.address = nil;

    NSURL *resources = NSBundle.mainBundle.resourceURL;
    NSTask *task = [NSTask new];
    task.executableURL = [resources URLByAppendingPathComponent:@"python/bin/python3"];
    task.arguments = @[@"-IB", [resources URLByAppendingPathComponent:@"desktop.py"].path];
    task.currentDirectoryURL = resources;
    NSPipe *output = [NSPipe pipe];
    task.standardOutput = output;
    NSError *error;
    if (![task launchAndReturnError:&error]) {
        [self showFailure:error.localizedDescription];
        return;
    }
    self.server = task;

    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        NSData *data = output.fileHandleForReading.availableData;
        NSString *line = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
        NSURL *url = [NSURL URLWithString:[line stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet] ?: @""];
        dispatch_async(dispatch_get_main_queue(), ^{
            if (self.server != task) return;
            if (task.running && [url.scheme isEqualToString:@"http"] && [url.host isEqualToString:@"127.0.0.1"] && url.port) {
                self.address = url;
                [NSWorkspace.sharedWorkspace openURL:url];
            } else {
                if (task.running) [task terminate];
                [self showFailure:@"Desk could not start its local server. Check that your Desk folder in Application Support is writable."];
            }
        });
    });
}

- (void)showFailure:(NSString *)details {
    NSAlert *alert = [NSAlert new];
    alert.messageText = @"Desk could not open";
    alert.informativeText = details;
    [alert runModal];
}

- (void)applicationWillTerminate:(NSNotification *)notification {
    if (self.server.running) [self.server terminate];
}
@end

int main(void) {
    @autoreleasepool {
        NSApplication *app = NSApplication.sharedApplication;
        DeskLauncher *delegate __attribute__((objc_precise_lifetime)) = [DeskLauncher new];
        app.delegate = delegate;
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        [app run];
    }
    return 0;
}
