#include "../launcher/json_fields.h"
#include <cassert>
int main() {
    assert(JsonField("{\n  \"bridge_token\": \"actual-token\"\n}", "bridge_token") == "actual-token");
    assert(JsonField("{\"bridge_token\":\"compact\"}", "bridge_token") == "compact");
    assert(JsonField("{\"status\": {\"bridge\": \"online\", \"target_id\": \"tab-123\", \"paused\": false}}", "bridge") == "online");
    assert(JsonField("{\"target_id\":\"tab-123\"}", "target_id") == "tab-123");
    assert(JsonField("{\"paused\": true}", "paused") == "true");
    assert(JsonField("{}", "missing").empty());
    assert(JsonField("{\"bridge_token\": \"", "bridge_token").empty());
    assert(JsonPort("{\"port\": 8766}") == 8766);
    assert(JsonPort("{\"port\": 0}") == 8765);
    assert(JsonPort("{}") == 8765);
}
