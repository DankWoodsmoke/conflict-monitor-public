/* Safe regression for zlib 1.4's invalid-window/reset dictionary fix.
 * Query length only: never write into the caller's documented 32 KiB buffer.
 * 1.3.2 incorrectly reports 65536 after rejecting an invalid window header. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zlib.h>
int main(void) {
    unsigned char input[98304], output[98304], invalid[2] = {0xf8, 0};
    unsigned long capacity = compressBound(sizeof(input));
    unsigned char *compressed = malloc(capacity);
    z_stream stream = {0};
    unsigned length = 0;
    int result;
    if (!compressed) return 2;
    memset(input, 'A', sizeof(input));
    while ((((unsigned)invalid[0] << 8) + invalid[1]) % 31) ++invalid[1];
    if (compress2(compressed, &capacity, input, sizeof(input), 6) != Z_OK) return 3;
    if (inflateInit2(&stream, 0) != Z_OK) return 4;
    stream.next_in = invalid; stream.avail_in = sizeof(invalid);
    stream.next_out = output; stream.avail_out = sizeof(output);
    if (inflate(&stream, Z_NO_FLUSH) != Z_DATA_ERROR) return 5;
    if (inflateReset(&stream) != Z_OK) return 6;
    stream.next_in = compressed; stream.avail_in = (unsigned)capacity;
    stream.next_out = output; stream.avail_out = 65536;
    if (inflate(&stream, Z_NO_FLUSH) != Z_OK || stream.avail_out != 0) return 10;
    if (inflateGetDictionary(&stream, NULL, &length) != Z_OK) return 8;
    stream.avail_out = 32768;
    result = inflate(&stream, Z_NO_FLUSH);
    if (result != Z_STREAM_END || stream.total_out != sizeof(input)
        || memcmp(input, output, sizeof(input))) return 7;
    printf("zlib=%s invalid_window_reset_dictionary_length=%u documented_maximum=32768\n", zlibVersion(), length);
    if (inflateEnd(&stream) != Z_OK) return 9;
    free(compressed);
    return length == 32768 ? 0 : 42;
}
