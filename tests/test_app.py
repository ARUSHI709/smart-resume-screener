import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch
from app import Candidate, llm_score, parse_resume, score, screen_candidate

class ScreeningTests(unittest.TestCase):
    def test_extracts_structured_fields(self):
        parsed = parse_resume('Jane Doe\nPython developer with 5 years experience. BS Computer Science. AWS and Docker.', 'jane.txt')
        self.assertEqual(parsed['name'], 'Jane Doe')
        self.assertEqual(parsed['experience_years'], 5)
        self.assertIn('python', parsed['skills'])
        self.assertIn("Bachelor's", parsed['education'])
    def test_matching_rewards_required_skills(self):
        c = Candidate(1, 'Jane', 'jane.txt', 'Python AWS Docker SQL engineer', ['python','aws','docker','sql'], 5, [], 'now')
        result = score(c, 'Need a Python engineer with AWS, Docker and 3 years experience.')
        self.assertGreaterEqual(result['score'], 8)
        self.assertEqual(result['missing_skills'], [])
        self.assertEqual(result['scoring_method'], 'rules_fallback')

    def test_uses_rule_score_when_llm_is_unavailable(self):
        c = Candidate(1, 'Jane', 'jane.txt', 'Python AWS', ['python', 'aws'], 3, [], 'now')
        with patch('app.llm_score', return_value=None):
            self.assertEqual(screen_candidate(c, 'Python and AWS'), score(c, 'Python and AWS'))

    def test_accepts_valid_structured_llm_result(self):
        class FakeOpenAI:
            def __init__(self):
                self.responses = SimpleNamespace(create=lambda **_: SimpleNamespace(output_text='{"score": 8.5, "matched_requirements": ["Python"], "gaps": ["Kubernetes"], "justification": "Python is documented in the resume."}'))
        c = Candidate(1, 'Jane', 'jane.txt', 'Python AWS', ['python', 'aws'], 3, [], 'now')
        with patch.dict(sys.modules, {'openai': SimpleNamespace(OpenAI=FakeOpenAI)}), patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}):
            result = llm_score(c, 'Python with Kubernetes')
        self.assertEqual(result['score'], 8.5)
        self.assertEqual(result['scoring_method'], 'llm')
if __name__ == '__main__': unittest.main()
