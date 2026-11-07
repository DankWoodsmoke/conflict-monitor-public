#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "libavutil/avstring.h"
#include "libavutil/encryption_info.h"
#include "libavutil/hdr_dynamic_metadata.h"
#include "libavutil/mem.h"

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    if (!strcmp(argv[1], "empty-search")) {
        char *out = av_strireplace("known text", "", "replacement");
        int ok = out && !strcmp(out, "known text");
        av_free(out);
        return ok ? 0 : 1;
    }
    if (!strcmp(argv[1], "deep-encryption-list")) {
        AVEncryptionInitInfo *head = NULL;
        for (int i = 0; i < 20000; i++) {
            AVEncryptionInitInfo *item = av_encryption_init_info_alloc(0, 0, 0, 0);
            if (!item) return 2;
            item->next = head;
            head = item;
        }
        av_encryption_init_info_free(head);
        return 0;
    }
    if (!strcmp(argv[1], "hdr-roundtrip")) {
        AVDynamicHDRPlus input = {0}, output = {0};
        uint8_t bytes[4096], *data = bytes;
        size_t size = sizeof(bytes);
        memset(bytes, 0xa5, sizeof(bytes));
        input.num_windows = 1;
        input.targeted_system_display_maximum_luminance = (AVRational){1000, 1};
        for (int i = 0; i < 3; i++) input.params[0].maxscl[i] = (AVRational){1, 1};
        input.params[0].average_maxrgb = (AVRational){1, 1};
        input.params[0].fraction_bright_pixels = (AVRational){0, 1};
        input.params[0].color_saturation_mapping_flag = 1;
        input.params[0].color_saturation_weight = (AVRational){31, 8};
        if (av_dynamic_hdr_plus_to_t35(&input, &data, &size) < 0) return 3;
        if (av_dynamic_hdr_plus_from_t35(&output, data, size) < 0) return 4;
        if (output.params[0].tone_mapping_flag || !output.params[0].color_saturation_mapping_flag
                || output.params[0].color_saturation_weight.num != 31
                || output.params[0].color_saturation_weight.den != 8) return 1;
        return 0;
    }
    return 2;
}
