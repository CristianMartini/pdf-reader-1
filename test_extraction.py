import os
import sys

# Garante que podemos importar do diretório atual
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web import _extract_text_from_pdf

def test_extraction():
    pdf_path = os.path.join("outputs", "teste.pdf")
    if not os.path.exists(pdf_path):
        print(f"❌ PDF de teste não encontrado em: {pdf_path}")
        sys.exit(1)
        
    print(f"🧪 Iniciando teste de extração no arquivo: {pdf_path}")
    
    try:
        extracted_text = _extract_text_from_pdf(pdf_path)
        
        print("\n--- TEXTO EXTRAÍDO ---")
        print(extracted_text)
        print("----------------------\n")
        
        # Validações básicas do teste
        assert "Disciplina" in extracted_text, "A palavra 'Disciplina' deveria estar no texto."
        assert "Aula 01" in extracted_text, "A palavra 'Aula 01' deveria estar no texto."
        assert "Material Didático" not in extracted_text, "O cabeçalho 'Material Didático' deveria ter sido filtrado por coordenadas (topo 8%)."
        
        # O número de página '2' (em outputs/teste.pdf) fica no rodapé (rodapé 8%), deve ser filtrado.
        # Vamos verificar se existe um numeral '2' isolado como linha.
        lines = [l.strip() for l in extracted_text.splitlines()]
        assert "2" not in lines, "O número de página '2' no rodapé deveria ter sido filtrado."
        
        print("✅ Teste concluído com SUCESSO! A extração por coordenadas e repetição funcionou perfeitamente.")
        
    except AssertionError as ae:
        print(f"❌ Falha na validação do teste: {ae}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Erro inesperado durante o teste: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_extraction()
