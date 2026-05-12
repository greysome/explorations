#include <assert.h>
#include <errno.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/random.h>
#include <time.h>

//#define DEBUG_PREGENERATE

// Minimal PCG32 generator by M.E. O'Neill
// ---------------------------------------

typedef struct {
  uint64_t state;
  uint64_t inc;
} Pcg;

static Pcg pcg;

uint32_t pcg_next(Pcg *pcg0) {
  uint64_t oldstate = pcg0->state;
  // Advance internal state
  pcg0->state = oldstate * 6364136223846793005ULL + (pcg0->inc|1);
  // Calculate output function (XSH RR), uses old state for max ILP
  uint32_t xorshifted = (uint32_t) (((oldstate >> 18u) ^ oldstate) >> 27u);
  uint32_t rot = (uint32_t) (oldstate >> 59u);
  return (xorshifted >> rot) | (xorshifted << ((-rot) & 31));
}

static inline uint32_t pcg_next_upto(Pcg *pcg0, uint32_t bound) {
  uint32_t x;
  while ((x = pcg_next(pcg0)) >= 4294967295 / bound * bound)
    ;
  return x % bound;
}

// Generation code
// ---------------

#define MAX_AREA 121

int cmp_int(const void *x, const void *y) {
  int a = *(int *)x;
  int b = *(int *)y;
  return a < b ? -1 : a > b ? 1 : 0;
}

static inline int adjacent_square(int sq, int w, int h, int dir) {
  int x = sq % w;
  int y = sq / w;
  assert(x >= 0 && x < w);
  assert(y >= 0 && y < h);
  assert(dir >= 0 && dir <= 8);
  if (dir == 0 && x > 0 && y > 0) return sq - w - 1;
  else if (dir == 1 && y > 0) return sq - w;
  else if (dir == 2 && x < w-1 && y > 0) return sq - w + 1;
  else if (dir == 3 && x > 0) return sq - 1;
  else if (dir == 4) return sq;
  else if (dir == 5 && x < w-1) return sq + 1;
  else if (dir == 6 && x > 0 && y < h-1) return sq + w - 1;
  else if (dir == 7 && y < h-1) return sq + w;
  else if (dir == 8 && x < w-1 && y < h-1) return sq + w + 1;
  else return -1;
}

void pregenerate_dense_board(int w, int h, int mine_count, int max_uncovered) {
  int area = w * h;
  assert(w >= 3 && h >= 3 && area <= 121);
  assert(mine_count >= 0 && mine_count <= area);
  int covered_counts[area] = { };
  int uncovered[area] = { };
  int mines[mine_count] = { };
  int mines_placed = 0;

  for (int sq = 0; sq < area; sq++) {
    if (mines_placed == mine_count) {
      break;
    }

    if ((int) pcg_next_upto(&pcg, area - sq) <= mine_count - mines_placed) {
      // Place a mine.
      mines[mines_placed++] = sq;
      // Cover the cells in the 3x3 grid.
      for (int dir = 0; dir < 9; dir++) {
        int adj_sq = adjacent_square(sq, w, h, dir);
        if (adj_sq != -1)
          covered_counts[adj_sq]++;
      }
    }
  }

  int uncovered_count;
  while (1) {
    uncovered_count = 0;
    // Populate uncovered array.
    for (int sq = 0; sq < area; sq++) {
      if (covered_counts[sq] == 0) {
        uncovered[uncovered_count++] = sq;
      }
    }

    assert(uncovered_count <= area - mine_count);
    if (uncovered_count <= max_uncovered)
      break;

    // Choose a random square adjacent to a random uncovered square.
    int uncovered_sq = uncovered[pcg_next_upto(&pcg, uncovered_count)];

    // Imagine placing a mine here; cover its 3x3 grid.
    for (int dir = 0; dir < 9; dir++) {
      int adj_sq = adjacent_square(uncovered_sq, w, h, dir);
      if (adj_sq != -1)
        covered_counts[adj_sq]++;
    }

    // Look for a redundant mine.
    for (int i = 0; i < mines_placed; i++) {
      bool is_redundant = true;
      int mine_sq = mines[i];

      // Redundant means all cells in 3x3 grid are covered more than once.
      for (int dir = 0; dir < 9; dir++) {
        int adj_sq = adjacent_square(mine_sq, w, h, dir);
        if (adj_sq != -1 && covered_counts[adj_sq] == 1) {
          is_redundant = false;
          break;
        }
      }

      if (is_redundant) {
        // Uncover the cells in the 3x3 grid.
        for (int dir = 0; dir < 9; dir++) {
          int adj_sq = adjacent_square(mine_sq, w, h, dir);
          if (adj_sq != -1)
            covered_counts[adj_sq]--;
        }

        // Replace the redundant mine with the adj_sq.
        mines[i] = uncovered_sq;
        break;
      }
    }
  }

#ifdef DEBUG_PREGENERATE
  qsort(mines, mine_count, sizeof(int), cmp_int);
  int *next_mine = &mines[0];

  for (int y = 0; y < h; y++) {
    for (int x = 0; x < w; x++) {
      int sq = y*w + x;
      if (sq == *next_mine) {
        putchar('X');
        if (next_mine - mines + 1 < mine_count)
          next_mine++;
      }
      else {
        putchar('.');
      }
    }
    putchar('\n');
  }
#endif
}

int main(int argc, char **argv) {
  assert(argc == 1 || argc == 3);
  if (argc == 3) {
    pcg.state = (uint64_t) strtoull(argv[1], NULL, 10);
    pcg.inc = (uint64_t) strtoull(argv[2], NULL, 10);
  }
  else {
    if (getentropy(&pcg.state, sizeof(uint64_t)) == -1 ||
        getentropy(&pcg.inc, sizeof(uint64_t)) == -1) {
      fprintf(stderr, "Error while getentropy() -- %s\n", strerror(errno));
      return EXIT_FAILURE;
    }
  }
  fprintf(stderr, "seed = %" PRIu64 " %" PRIu64 "\n", pcg.state, pcg.inc);

  int w = 11;
  int h = 11;
  int mine_count = 30;
  int max_uncovered = 0;
  int n_boards = 100000;

  struct timespec ts_start;
  struct timespec ts_end;
  clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &ts_start);
  // Profile start
  for (int i = 0; i < n_boards; i++)
    pregenerate_dense_board(w, h, mine_count, max_uncovered);
  // Profile end
  clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &ts_end);

  double elapsed = (double)(ts_end.tv_sec - ts_start.tv_sec) +
    (double)(ts_end.tv_nsec - ts_start.tv_nsec) / 1000000000;
  fprintf(stderr, "%fs to generate %d boards (%fus per board)\n", elapsed, n_boards, elapsed / n_boards * 1000000);
}