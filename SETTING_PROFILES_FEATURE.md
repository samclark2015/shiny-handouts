# Setting Profiles Feature

## Overview

Setting Profiles allow users to create multiple named configurations for different lecture types or courses. Each profile can have custom prompts and spreadsheet columns tailored to specific subjects (e.g., Pathology, Cardiology, Anatomy).

**Note:** The old `UserSettings` model has been removed. All settings are now managed through SettingProfile.

## Implementation Summary

### Models

#### SettingProfile Model (`accounts/models.py`)
- **Fields:**
  - `user`: ForeignKey to User
  - `name`: CharField - Profile name (e.g., "Pathology", "Cardiology")
  - `is_default`: BooleanField - Mark profile as default for the user
  - `vignette_prompt`: TextField - Custom vignette generation prompt
  - `spreadsheet_prompt`: TextField - Custom spreadsheet generation prompt
  - `spreadsheet_columns`: JSONField - Custom Excel columns configuration
  - `created_at`, `updated_at`: Timestamps

- **Key Features:**
  - Unique together constraint on (user, name)
  - Automatic default management (only one default per user)
  - Ordered by name

#### Job Model Update (`core/models.py`)
- Added `setting_profile` ForeignKey field (nullable)
- Links each job to the profile used for generation

### Views

#### Profile Management (`accounts/views.py`)
- `profiles_view`: List all user's profiles
- `profile_create`: Create a new profile
- `profile_edit`: Edit an existing profile
- `profile_delete`: Delete a profile (HTMX/AJAX)

#### Generation Views (`core/views/api.py`)
Updated all three processing views to accept `profile_id`:
- `upload_file`
- `process_url`
- `process_panopto`

#### Main View (`core/views/main.py`)
- Updated to pass user's profiles and default profile to template

### URLs

New URL patterns in `accounts/urls.py`:
- `/auth/profiles/` - List profiles
- `/auth/profiles/create/` - Create profile
- `/auth/profiles/<id>/edit/` - Edit profile
- `/auth/profiles/<id>/delete/` - Delete profile (DELETE method)

### Templates

#### New Templates
1. **profiles.html**: Profile management page
   - Lists all user profiles
   - Shows default profile badge
   - Displays profile details (prompts, columns)
   - Delete functionality with confirmation

2. **profile_form.html**: Create/Edit profile form
   - Profile name input
   - Default checkbox
   - Vignette prompt textarea
   - Spreadsheet prompt textarea
   - Column editor (drag-and-drop reordering)

#### Updated Templates
1. **output_options.html**: Added profile selector dropdown
   - Shows all profiles with default pre-selected
   - Includes link to manage profiles

2. **settings.html**: Added info banner and link to profiles page

### Forms

#### SettingProfileForm (`accounts/forms.py`)
- Handles profile creation and editing
- Parses JSON column configuration from hidden field
- Validates and normalizes column data

### Admin

#### SettingProfileAdmin (`accounts/admin.py`)
- Full admin interface for managing profiles
- List display with custom columns
- Filtering and searching
- Raw ID field for user selection

### Migrations

1. **accounts/0004_settingprofile.py**: Creates SettingProfile table
2. **core/0004_job_setting_profile.py**: Adds setting_profile FK to Job
3. **accounts/0005_remove_usersettings.py**: Removes deprecated UserSettings table

## Usage

### For Users

1. **Create a Profile:**
   - Navigate to Profiles (from dashboard header)
   - Click "Create New Profile"
   - Enter a name (e.g., "Pathology")
   - Optionally customize prompts and columns
   - Set as default if desired

2. **Use a Profile:**
   - When generating a handout, expand "Output Options"
   - Select the desired profile from the dropdown
   - The default profile is pre-selected

3. **Manage Profiles:**
   - Edit: Click edit icon on profile card
   - Delete: Click delete icon and confirm
   - Set Default: Check "Set as default" in edit form

**Important:** Every job should use a profile. If no profile is selected during generation, the job will use system defaults.

### For Developers

#### Accessing Profile Settings in Tasks
When processing a job, access the profile settings:

```python
job = Job.objects.get(pk=job_id)
if job.setting_profile:
    vignette_prompt = job.setting_profile.get_vignette_prompt()
    spreadsheet_prompt = job.setting_profile.get_spreadsheet_prompt()
    columns = job.setting_profile.get_spreadsheet_columns()
else:
    # No profile - use system defaults
    vignette_prompt = None
    spreadsheet_prompt = None
    columns = None
```

#### Creating a Profile Programmatically
```python
from accounts.models import SettingProfile

profile = SettingProfile.objects.create(
    user=request.user,
    name="Cardiology",
    is_default=True,
    vignette_prompt="Custom prompt...",
    spreadsheet_columns=[
        {"name": "Condition", "description": "The disease name"},
        {"name": "Symptoms", "description": "Clinical presentation"}
    ]
)
```

## Database Schema

```sql
-- Setting Profiles Table
CREATE TABLE setting_profiles (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    is_default BOOLEAN DEFAULT FALSE,
    vignette_prompt TEXT,
    spreadsheet_prompt TEXT,
    spreadsheet_columns JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, name)
);

-- Job Update
ALTER TABLE jobs ADD COLUMN setting_profile_id BIGINT 
    REFERENCES setting_profiles(id) ON DELETE SET NULL;
```

## Future Enhancements

Potential improvements:
1. Profile templates/sharing between users
2. Import/export profiles as JSON
3. Profile usage statistics
4. Clone profile functionality
5. Profile categories/tags
6. Bulk operations on profiles
