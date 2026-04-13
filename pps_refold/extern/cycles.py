from __future__ import annotations

from ..models import MoveOp


def detect_move_cycles(moves: list[MoveOp]) -> bool:
    adj: dict[str, str] = {m.source: m.destination for m in moves}
    visited: set[str] = set()
    in_stack: set[str] = set()

    for start in adj:
        if start in visited:
            continue
        stack = [start]
        while stack:
            node = stack[-1]
            if node not in visited:
                visited.add(node)
                in_stack.add(node)
                nxt = adj.get(node)
                if nxt is not None:
                    if nxt in in_stack:
                        return True
                    if nxt not in visited:
                        stack.append(nxt)
                        continue
            in_stack.discard(node)
            stack.pop()

    return False
