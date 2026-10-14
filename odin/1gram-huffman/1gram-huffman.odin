package onegram_huffman

import "core:fmt"
import "core:math"
import "core:os"
import "core:strings"
import "core:terminal/ansi"

find_min2 :: proc(arr: []int) -> (int, int) {
  m1 := 100
  m2 := 100
  i: int
  j: int

  // First pass
  for x, idx in arr {
    if x < m1 {
      m1 = x
      i = idx
    }
  }

  // Second pass
  for x, idx in arr {
    if x < m2 && idx != i {
      m2 = x
      j = idx
    }
  }

  return i, j
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

  // 26 leaf nodes + 25 non-leaf nodes
  counts: [26+25]int
  lchilds: [26+25]int
  count_ignored: int

  for b in buf[:n] {
    c := b
    if c >= 'a' && c <= 'z' {
      c -= 'a' - 'A'
    }
    if c >= 'A' && c <= 'Z' {
      counts[c - 'A'] += 1
    }
    else {
      count_ignored += 1
    }
  }

  if count_ignored > 0 {
    fmt.printf(ansi_info + "Ignored %d non-letter chars\n" + ansi_reset,
              count_ignored)
  }

  for i in 0..<26 {
    lchilds[i] = -i - 1
  }

  // Populate the Huffman tree
  //
  // The interval [start,end] defines a 'window' of nodes that are
  // in consideration at the current timestep.
  //
  // We then combine the two smallest nodes, and flush them to the
  // left of the window. Then, we append a new node at index end+1
  // (representing the combination of the two smallest nodes)
  // and update the window to [start+2,end+1].

  start := 0
  end := 26

  for t in 0..<25 {
    counts_window := counts[start:end]
    lchilds_window := lchilds[start:end]

    i, j := find_min2(counts_window)

    counts_window[0], counts_window[i] = counts_window[i], counts_window[0]
    counts_window[1], counts_window[j] = counts_window[j], counts_window[1]
    lchilds_window[0], lchilds_window[i] = lchilds_window[i], lchilds_window[0]
    lchilds_window[1], lchilds_window[j] = lchilds_window[j], lchilds_window[1]

    counts[end] = counts_window[0] + counts_window[1]
    lchilds[end] = start

    start += 2
    end += 1
  }

  // Derive the codes via a DFS traversal of the Huffman tree

  StackEntry :: struct {
    idx: int,
    code_sb: strings.Builder
  }
  codes: [26]string
  stack: [26]StackEntry
  stack[0] = StackEntry{idx=26+24, code_sb=strings.builder_make()}
  stack_ptr := 0

  for stack_ptr >= 0 {
    entry := stack[stack_ptr]
    stack_ptr -= 1
    idx := entry.idx

    // Negative pointers represent leaf nodes
    if lchilds[idx] < 0 {
      letter := -lchilds[idx] - 1
      //fmt.println(entry, letter)
      codes[letter] = strings.to_string(entry.code_sb)
      continue
    }

    lchild := lchilds[idx]
    rchild := lchild + 1
    //fmt.println(entry, lchild, rchild)
    lcode_sb := entry.code_sb
    rcode_sb := strings.builder_make()
    fmt.sbprint(&rcode_sb, strings.to_string(lcode_sb))
    strings.write_byte(&lcode_sb, '0')
    strings.write_byte(&rcode_sb, '1')

    stack_ptr += 1
    stack[stack_ptr] = StackEntry{idx=lchild, code_sb=lcode_sb}
    stack_ptr += 1
    stack[stack_ptr] = StackEntry{idx=rchild, code_sb=rcode_sb}
  }

  for code, idx in codes {
    fmt.printf("%c: %v\n", idx + 'A', code)
  }
}