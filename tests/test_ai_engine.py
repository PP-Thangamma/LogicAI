import unittest
from services.ai_engine import analyze_ticket, similarity
class AITests(unittest.TestCase):
    def test_network(self): self.assertEqual(analyze_ticket('Wi-Fi is not connecting')['category'],'Networking')
    def test_critical(self): self.assertEqual(analyze_ticket('The whole college network is down')['priority'],'Critical')
    def test_hardware(self): self.assertEqual(analyze_ticket('My keyboard is not working')['department'],'Hardware')
    def test_electrical(self): self.assertEqual(analyze_ticket('Power outage and circuit breaker issue')['category'],'Electrical')
    def test_low_confidence(self): self.assertTrue(analyze_ticket('Something is wrong in my room')['review_required'])
    def test_similarity(self): self.assertGreater(similarity('wifi not working in block b','wifi is not working block b'),.45)
if __name__=='__main__': unittest.main()
