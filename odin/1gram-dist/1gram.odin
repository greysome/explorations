package onegram_dist

import "core:fmt"
import "core:math"
import "core:os"
import "core:terminal/ansi"

entropy :: proc(P: [26]f32) -> f32 {
  h : f32 = 0
  for p in P {
    assert(0 <= p && p <= 1)
    if p > 0 {
      h -= p * math.log2_f32(p)
    }
  }
  return h
}

divergence :: proc(P: [26]f32, Q: [26]f32) -> f32 {
  d : f32 = 0
  for i in 0..<26 {
    p := P[i]
    q := Q[i]
    assert(0 <= p && p <= 1)
    assert(0 <= q && q <= 1)
    if q == 0 && p > 0 {
      return math.INF_F32
    }
    if p > 0 {
      d += p * math.log2_f32(p / q)
    }
  }
  return d
}

main :: proc() {
  buf: [1024]byte
  dummybuf: [1024]byte
  ansi_info :: ansi.CSI + ansi.FG_YELLOW + ansi.SGR
  ansi_reset :: ansi.CSI + ansi.RESET + ansi.SGR

  fmt.print("Enter your message: ")
  n, err := os.read(os.stdin, buf[:])
  if err != nil {
    return
  }

  if buf[n-1] != '\n' {
    fmt.println(ansi_info + "Truncating input line to 1024 chars" + ansi_reset)
    for {
      nn, err := os.read(os.stdin, dummybuf[:])
      if err != nil {
        return
      }
      if dummybuf[nn-1] == '\n' {
        break
      }
    }
  }
  else {
    // Exclude the trailing newline
    n -= 1
  }

  counts: [26]int
  count_ignored: int

  for b in buf[:n] {
    c := b
    if c >= 97 && c <= 122 {
      c -= 32
    }
    if c >= 65 && c <= 90 {
      counts[c-65] += 1
    }
    else {
      count_ignored += 1
    }
  }

  if count_ignored > 0 {
    fmt.printf(ansi_info + "Ignored %d non-letter chars\n" + ansi_reset,
              count_ignored)
  }

  input_dist: [26]f32
  // Taken from https://en.wikipedia.org/wiki/Letter_frequency
  reference_dist:= [26]f32{0.082, 0.015, 0.028, 0.043, 0.127,
                           0.022, 0.020, 0.061, 0.070, 0.0016,
                           0.0077, 0.040, 0.024, 0.067, 0.075,
                           0.019, 0.0012, 0.060, 0.063, 0.091,
                           0.028, 0.0098, 0.024, 0.0015, 0.02,
                           0.00074}

  for i in 0..<26 {
    input_dist[i] = f32(counts[i]) / f32(n)
  }

  fmt.printf("H(input) = %f\n", entropy(input_dist))
  fmt.printf("H(reference) = %f\n", entropy(reference_dist))
  fmt.printf("D(input||reference) = %f\n", divergence(input_dist, reference_dist))
}