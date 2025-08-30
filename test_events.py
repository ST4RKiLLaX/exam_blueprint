from app.utils.event_parser import get_available_categories, get_upcoming_events

print('Available categories:', get_available_categories())
for cat in get_available_categories():
    print(f'\n{cat} events:')
    print('\n'.join(get_upcoming_events(cat)))