CC := gcc
CFLAGS := -std=c23 -D_XOPEN_SOURCE=500 -lm -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Wdouble-promotion -Wno-sign-conversion -Wno-unused-variable

ifdef RELEASE
	BUILD := release
	CFLAGS += -O3 -march=native
else
	BUILD := debug
	CFLAGS += -g -fsanitize=address -fsanitize=undefined
endif

.PHONY: clean

a.out: gen_board.c
	$(CC) $(CFLAGS) $< -o $@

clean:
	rm a.out