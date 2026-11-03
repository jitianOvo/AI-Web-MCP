#include "../launcher/main.cpp"
#include <iostream>

int wmain(int argc, wchar_t** argv) {
    if (argc != 2) return 2;
    g_root = argv[1];
    ReadConfig();
    RefreshStatus();
    if (!g_status_error.empty()) return 3;
    const bool originalPaused = g_paused;
    const bool pauseSent = HttpPost(L"/api/pause");
    RefreshStatus();
    const bool paused = pauseSent && g_paused && g_status_error.empty();
    const bool resumeSent = HttpPost(L"/api/resume");
    RefreshStatus();
    const bool resumed = resumeSent && !g_paused && g_status_error.empty();
    const bool restored = !originalPaused || HttpPost(L"/api/pause");
    std::cout << "pause=" << paused << " resume=" << resumed << " restored=" << restored << '\n';
    return paused && resumed && restored ? 0 : 1;
}
