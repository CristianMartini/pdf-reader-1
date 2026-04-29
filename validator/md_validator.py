"""
Validador rigoroso de markdown — validator/md_validator.py
O validador manda no sistema. Falha = processo para.
"""

import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class ValidationResult:
    errors: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def __str__(self) -> str:
        if self.is_valid:
            return "✅ Conteúdo válido"
        return "❌ Erros:\n" + "\n".join(f"  - {e}" for e in self.errors)


def validate(md: str) -> ValidationResult:
    """
    Valida o markdown gerado pelo Gemini.
    Regras rigorosas: estrutura mínima + padrões proibidos.
    """
    result = ValidationResult()

    # ── Estrutura mínima ──
    h1_count = len(re.findall(r"^# ", md, re.MULTILINE))
    if h1_count < 3:
        result.errors.append(f"Poucas seções H1 (encontrado: {h1_count}, mínimo: 3)")

    if "[BOX]" not in md:
        result.errors.append("Nenhum [BOX] encontrado — obrigatório mínimo 1")

    img_count = len(re.findall(r"\[IMG:", md))
    if img_count < 2:
        result.errors.append(f"Poucas imagens (encontrado: {img_count}, mínimo: 2)")

    # ── Tamanho mínimo ──
    word_count = len(md.split())
    if word_count < 2000:
        result.errors.append(f"Conteúdo insuficiente ({word_count} palavras, mínimo: 2000)")

    # ── Padrões proibidos ──
    if "<" in md and ">" in md:
        result.errors.append("HTML detectado no markdown — proibido")

    if re.search(r"https?://", md):
        result.errors.append("Links externos detectados — proibido")

    # ── BOX balanceado ──
    open_count = md.count("[BOX]")
    close_count = md.count("[/BOX]")
    if open_count != close_count:
        result.errors.append(
            f"[BOX] não balanceado: {open_count} aberturas, {close_count} fechamentos"
        )

    return result
