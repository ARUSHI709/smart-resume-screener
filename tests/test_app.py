import unittest
from app import Candidate, find_skills, parse_resume, score

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
if __name__ == '__main__': unittest.main()
