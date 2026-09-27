#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <wininet.h>
#include <string>
#include <cstdio>

#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "wininet.lib")
#pragma comment(lib, "advapi32.lib")

static const wchar_t* MAIN_CLASS = L"GPTWebMCPMainWindow";
static const wchar_t* MSG_CLASS = L"GPTWebMCPMsgWindow";
static const int IDM_SHOW = 1;
static const int IDM_TOGGLE = 2;
static const int IDM_EXIT = 3;
static const int TRAY_ID = 1;
static const UINT WM_TRAY = WM_APP + 1;

static HWND g_main = 0;
static HWND g_msgwin = 0;
static HICON g_icon = 0;
static HANDLE g_child = 0;
static HANDLE g_mutex = 0;
static bool g_paused = false;
static bool g_force_exit = false;
static std::wstring g_root;
static std::wstring g_token;
static std::wstring g_status_bridge = L"-";
static std::wstring g_status_ext = L"-";
static std::wstring g_status_page = L"-";
static std::wstring g_status_state = L"-";
static std::wstring g_status_target = L"-";
static HGLOBAL g_hText = 0;

static std::wstring ExeDir() {
    wchar_t buf[MAX_PATH];
    DWORD n = GetModuleFileNameW(0, buf, MAX_PATH);
    std::wstring p(buf, n);
    size_t pos = p.find_last_of(L"\\/");
    return pos == std::wstring::npos ? L"." : p.substr(0, pos);
}

static std::wstring ReadConfigToken() {
    std::wstring path = g_root + L"\\config\\config.json";
    FILE* f = _wfopen(path.c_str(), L"rb");
    if (!f) return L"";
    std::string raw;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), f)) > 0) raw.append(buf, n);
    fclose(f);
    std::string key = "\"bridge_token\":\"";
    size_t a = raw.find(key);
    if (a == std::string::npos) return L"";
    a += key.size();
    size_t b = raw.find('"', a);
    if (b == std::string::npos) return L"";
    std::string tok = raw.substr(a, b - a);
    std::wstring out;
    for (char c : tok) out += (wchar_t)(unsigned char)c;
    return out;
}

static std::wstring HttpGet(const wchar_t* path) {
    std::wstring out;
    HINTERNET inet = InternetOpenW(L"GPT-Web-MCP", INTERNET_OPEN_TYPE_PRECONFIG, 0, 0, 0);
    if (!inet) return out;
    std::wstring url = L"http://127.0.0.1:8765" + std::wstring(path);
    HINTERNET conn = InternetOpenUrlW(inet, url.c_str(), 0, 0,
        INTERNET_FLAG_RELOAD | INTERNET_FLAG_NO_CACHE_WRITE, 0);
    if (!conn) { InternetCloseHandle(inet); return out; }
    char buf[8192];
    DWORD rd = 0;
    while (InternetReadFile(conn, buf, sizeof(buf) - 1, &rd) && rd > 0) {
        buf[rd] = 0;
        out += std::wstring((wchar_t*)buf, (wchar_t*)buf + rd);
    }
    InternetCloseHandle(conn);
    InternetCloseHandle(inet);
    return out;
}

static bool HttpPost(const wchar_t* path) {
    HINTERNET inet = InternetOpenW(L"GPT-Web-MCP", INTERNET_OPEN_TYPE_PRECONFIG, 0, 0, 0);
    if (!inet) return false;
    std::wstring url = L"http://127.0.0.1:8765" + std::wstring(path);
    HINTERNET conn = InternetOpenUrlW(inet, url.c_str(), 0, 0,
        INTERNET_FLAG_RELOAD | INTERNET_FLAG_NO_CACHE_WRITE, 0);
    if (!conn) { InternetCloseHandle(inet); return false; }
    std::wstring headers = L"X-Bridge-Token: " + g_token + L"\r\n";
    HttpSendRequestW(conn, headers.c_str(), (DWORD)-1L, 0, 0);
    InternetCloseHandle(conn);
    InternetCloseHandle(inet);
    return true;
}

static bool BridgeOnline() {
    if (g_token.empty()) return false;
    std::wstring r = HttpGet(L"/api/status");
    return r.find(L"\"bridge\":\"online\"") != std::wstring::npos;
}

static void RefreshStatus() {
    if (g_token.empty()) return;
    std::wstring r = HttpGet(L"/api/status");
    g_status_bridge = r.find(L"\"bridge\":\"online\"") != std::wstring::npos ? L"在线" : L"离线";
    g_status_ext = r.find(L"\"extension\":\"connected\"") != std::wstring::npos ? L"已连接" : L"未连接";
    g_status_page = r.find(L"\"page\":\"ready\"") != std::wstring::npos ? L"就绪" : L"未就绪";
    g_status_state = L"idle";
    size_t sp = r.find(L"\"response_state\":\"");
    if (sp != std::wstring::npos) {
        sp += 19;
        size_t se = r.find(L"\"", sp);
        if (se != std::wstring::npos) g_status_state = r.substr(sp, se - sp);
    }
    std::wstring tt = L"未绑定";
    size_t tp = r.find(L"\"target_id\":\"");
    if (tp != std::wstring::npos) {
        tp += 13;
        size_t te = r.find(L"\"", tp);
        if (te != std::wstring::npos) {
            std::wstring v = r.substr(tp, te - tp);
            if (v != L"unbound" && !v.empty()) tt = v;
        }
    }
    g_status_target = tt;
}

static void UpdateMainText(HWND hwnd) {
    std::wstring text =
        L"版本 0.1.29\r\n\r\n"
        L"桥服务: " + g_status_bridge + L"\r\n"
        L"扩展:   " + g_status_ext + L"\r\n"
        L"页面:   " + g_status_page + L"\r\n"
        L"任务:   " + g_status_state + L"\r\n"
        L"绑定:   " + g_status_target + L"\r\n\r\n"
        L"关闭窗口只隐藏到托盘，服务继续运行。\r\n"
        L"右键托盘图标可显示窗口 / 开始·暂停 / 退出程序。";
    if (g_hText) GlobalFree(g_hText);
    size_t bytes = (text.size() + 1) * sizeof(wchar_t);
    g_hText = GlobalAlloc(GMEM_MOVEABLE, bytes);
    if (g_hText) {
        void* dst = GlobalLock(g_hText);
        if (dst) {
            memcpy(dst, text.c_str(), bytes);
            GlobalUnlock(g_hText);
        }
    }
    InvalidateRect(hwnd, 0, TRUE);
}

static void StartBridge() {
    if (BridgeOnline()) return;
    std::wstring python = g_root + L"\\runtime\\venv\\Scripts\\python.exe";
    if (GetFileAttributesW(python.c_str()) == INVALID_FILE_ATTRIBUTES) {
        python = L"python";
    }
    SetEnvironmentVariableW(L"PYTHONPATH", (g_root + L"\\src").c_str());
    std::wstring cmd = L"\"" + python + L"\" -m gpt_web_mcp.bridge";
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    ZeroMemory(&pi, sizeof(pi));
    if (CreateProcessW(0, &cmd[0], 0, 0, FALSE, CREATE_NO_WINDOW, 0, g_root.c_str(), &si, &pi)) {
        g_child = pi.hProcess;
        CloseHandle(pi.hThread);
    }
}

static void StopBridge(bool graceful) {
    if (graceful && !g_token.empty()) {
        HttpPost(L"/api/shutdown");
        Sleep(1200);
    }
    if (g_child) {
        if (WaitForSingleObject(g_child, 0) == WAIT_TIMEOUT) {
            TerminateProcess(g_child, 0);
        }
        CloseHandle(g_child);
        g_child = 0;
    }
}

static void ToggleService() {
    if (g_paused) {
        HttpPost(L"/api/resume");
        g_paused = false;
    } else {
        bool online = BridgeOnline();
        if (!online) {
            StartBridge();
            Sleep(800);
        }
        HttpPost(L"/api/pause");
        g_paused = true;
    }
    RefreshStatus();
    UpdateMainText(g_main);
}

static void ShowMainWindow(bool show) {
    if (!g_main) return;
    if (show) {
        ShowWindow(g_main, SW_SHOW);
        ShowWindow(g_main, SW_RESTORE);
        SetForegroundWindow(g_main);
    } else {
        ShowWindow(g_main, SW_HIDE);
    }
    RefreshStatus();
    UpdateMainText(g_main);
}

static void UpdateTrayIcon() {
    NOTIFYICONDATAW nid;
    ZeroMemory(&nid, sizeof(nid));
    nid.cbSize = sizeof(nid);
    nid.hWnd = g_msgwin;
    nid.uID = TRAY_ID;
    nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
    nid.uCallbackMessage = WM_TRAY;
    nid.hIcon = g_icon;
    wcscpy_s(nid.szTip, L"GPT Web MCP Bridge");
    Shell_NotifyIconW(NIM_ADD, &nid);
    Shell_NotifyIconW(NIM_SETVERSION, &nid);
}

static void RemoveTrayIcon() {
    NOTIFYICONDATAW nid;
    ZeroMemory(&nid, sizeof(nid));
    nid.cbSize = sizeof(nid);
    nid.hWnd = g_msgwin;
    nid.uID = TRAY_ID;
    Shell_NotifyIconW(NIM_DELETE, &nid);
}

static void ShowTrayMenu() {
    HMENU menu = CreatePopupMenu();
    bool main_visible = IsWindowVisible(g_main) != 0;
    AppendMenuW(menu, MF_STRING | (main_visible ? MF_CHECKED : 0), IDM_SHOW,
        main_visible ? L"显示窗口 ✓" : L"显示窗口");
    AppendMenuW(menu, MF_STRING | (g_paused ? 0 : MF_CHECKED), IDM_TOGGLE,
        g_paused ? L"开始服务" : L"暂停服务");
    AppendMenuW(menu, MF_SEPARATOR, 0, 0);
    AppendMenuW(menu, MF_STRING, IDM_EXIT, L"退出程序");
    POINT pt;
    GetCursorPos(&pt);
    SetForegroundWindow(g_msgwin);
    UINT sel = TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, pt.x, pt.y, 0, g_msgwin, 0);
    DestroyMenu(menu);
    if (sel == IDM_SHOW) {
        ShowMainWindow(!main_visible);
    } else if (sel == IDM_TOGGLE) {
        ToggleService();
    } else if (sel == IDM_EXIT) {
        g_force_exit = true;
        PostMessageW(g_msgwin, WM_DESTROY, 0, 0);
    }
}

static LRESULT CALLBACK MsgProc(HWND hwnd, UINT msg, WPARAM w, LPARAM l) {
    if (msg == WM_TRAY) {
        if (l == WM_LBUTTONUP || l == WM_LBUTTONDBLCLK) {
            ShowMainWindow(!(IsWindowVisible(g_main) != 0));
        } else if (l == WM_RBUTTONUP) {
            ShowTrayMenu();
        }
        return 0;
    }
    if (msg == WM_DESTROY) {
        // Always stop the child bridge on any destroy path (tray exit, system
        // shutdown, task-manager close) so the user keeps full control.
        StopBridge(true);
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(hwnd, msg, w, l);
}

static LRESULT CALLBACK MainProc(HWND hwnd, UINT msg, WPARAM w, LPARAM l) {
    switch (msg) {
        case WM_PAINT: {
            PAINTSTRUCT ps;
            HDC dc = BeginPaint(hwnd, &ps);
            HBRUSH bg = CreateSolidBrush(RGB(245, 246, 250));
            FillRect(dc, &ps.rcPaint, bg);
            DeleteObject(bg);
            SetBkMode(dc, TRANSPARENT);
            HFONT font = CreateFontW(-16, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET,
                0, 0, CLEARTYPE_QUALITY, 0, L"Microsoft YaHei UI");
            HFONT title = CreateFontW(-22, 0, 0, 0, FW_SEMIBOLD, 0, 0, 0, DEFAULT_CHARSET,
                0, 0, CLEARTYPE_QUALITY, 0, L"Microsoft YaHei UI");
            RECT rc;
            GetClientRect(hwnd, &rc);
            const wchar_t* head = L"GPT Web MCP Bridge";
            rc.left += 16;
            rc.top += 6;
            HFONT old = (HFONT)SelectObject(dc, title);
            SetTextColor(dc, RGB(30, 60, 110));
            DrawTextW(dc, head, -1, &rc, DT_LEFT | DT_TOP | DT_NOPREFIX);
            rc.top += 34;
            SelectObject(dc, font);
            SetTextColor(dc, RGB(40, 45, 55));
            if (g_hText) {
                void* p = GlobalLock(g_hText);
                if (p) {
                    DrawTextW(dc, (const wchar_t*)p, -1, &rc, DT_LEFT | DT_TOP | DT_NOPREFIX | DT_WORDBREAK);
                    GlobalUnlock(g_hText);
                }
            }
            SelectObject(dc, old);
            DeleteObject(font);
            DeleteObject(title);
            EndPaint(hwnd, &ps);
            return 0;
        }
        case WM_CLOSE:
            ShowMainWindow(false);
            return 0;
    }
    return DefWindowProcW(hwnd, msg, w, l);
}

int APIENTRY wWinMain(HINSTANCE hInst, HINSTANCE, PWSTR, int) {
    g_root = ExeDir();
    size_t slash = g_root.rfind(L'\\');
    if (slash != std::wstring::npos) g_root = g_root.substr(0, slash);
    g_token = ReadConfigToken();

    g_mutex = CreateMutexW(0, TRUE, L"GPT-Web-MCP-SingleInstance");
    if (g_mutex && GetLastError() == ERROR_ALREADY_EXISTS) {
        HWND other = FindWindowW(MAIN_CLASS, 0);
        if (other) { ShowWindow(other, SW_SHOW); SetForegroundWindow(other); }
        return 0;
    }

    std::wstring ico = g_root + L"\\res\\GPT_Web_MCP_iconic.ico";
    g_icon = (HICON)LoadImageW(0, ico.c_str(), IMAGE_ICON, 32, 32, LR_LOADFROMFILE);
    if (!g_icon) g_icon = LoadIconW(0, IDI_APPLICATION);

    WNDCLASSW wm;
    ZeroMemory(&wm, sizeof(wm));
    wm.lpfnWndProc = MainProc;
    wm.hInstance = hInst;
    wm.hIcon = g_icon;
    wm.lpszClassName = MAIN_CLASS;
    RegisterClassW(&wm);

    WNDCLASSW wc;
    ZeroMemory(&wc, sizeof(wc));
    wc.lpfnWndProc = MsgProc;
    wc.hInstance = hInst;
    wc.lpszClassName = MSG_CLASS;
    RegisterClassW(&wc);

    g_main = CreateWindowExW(0, MAIN_CLASS, L"GPT Web MCP Bridge",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
        CW_USEDEFAULT, CW_USEDEFAULT, 520, 340, 0, 0, hInst, 0);
    g_msgwin = CreateWindowExW(0, MSG_CLASS, L"tray", 0, 0, 0, 0, 0,
        HWND_MESSAGE, 0, hInst, 0);

    UpdateTrayIcon();
    ShowMainWindow(true);
    StartBridge();

    SetTimer(g_msgwin, 2, 2000, 0);
    MSG msg;
    while (GetMessageW(&msg, 0, 0, 0)) {
        if (msg.message == WM_TIMER && msg.wParam == 2) {
            RefreshStatus();
            UpdateMainText(g_main);
        }
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }

    RemoveTrayIcon();
    if (g_icon) DestroyIcon(g_icon);
    if (g_hText) GlobalFree(g_hText);
    if (g_mutex) CloseHandle(g_mutex);
    return 0;
}
